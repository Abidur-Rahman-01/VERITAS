import json
import time
from pathlib import Path

from .io import canonical, digest, file_hash, read_records, write_json, write_jsonl
from .schema import Usage


def critic_text(row):
    # This explicit allowlist prevents outcome, verdict, gold answer and label leakage.
    return canonical({"context": row["context"], "action": row["action"]}).decode()


def training_rows(records, scope="semantic"):
    rows = [
        r
        for r in read_records(records)
        if r["split"] == "calib"
        and r.get("calibration_role") == "critic_train"
        and not r.get("blocked")
        and r.get("label_scope") == scope
        and r.get("error_label") is not None
    ]
    if len(rows) < 10 or len({r["error_label"] for r in rows}) < 2:
        raise ValueError(
            "Critic training needs >=10 independently labeled natural actions, with both classes"
        )
    return rows


def train_linear(records, output, scope="semantic", seed=42):
    import joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    rows = training_rows(records, scope)
    model = Pipeline(
        [
            ("text", TfidfVectorizer(max_features=100000, ngram_range=(1, 2), sublinear_tf=True)),
            ("classifier", LogisticRegression(max_iter=1000, random_state=seed)),
        ]
    )
    model.fit([critic_text(r) for r in rows], [r["error_label"] for r in rows])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output / "critic.joblib")
    write_json(
        output / "metadata.json",
        {
            "backend": "linear",
            "label_scope": scope,
            "fit_groups": sorted({r["group_id"] for r in rows}),
            "n": len(rows),
            "seed": seed,
            "weights_sha256": {"critic.joblib": file_hash(output / "critic.joblib")},
            "source_sha256": file_hash(Path(records)),
        },
    )


class TrainedCritic:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.metadata = json.loads((self.directory / "metadata.json").read_text())
        for name, expected in self.metadata.get("weights_sha256", {}).items():
            if file_hash(self.directory / name) != expected:
                raise ValueError("Critic weight checksum mismatch")
        if self.metadata["backend"] == "linear":
            import joblib

            # Load only your own artifact; pickle/joblib is executable serialization.
            self.model = joblib.load(self.directory / "critic.joblib")
        else:
            from peft import AutoPeftModelForSequenceClassification
            from transformers import AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
            self.model = AutoPeftModelForSequenceClassification.from_pretrained(
                directory, local_files_only=True, device_map="auto"
            )
            self.model.eval()

    def score(self, context, action):
        started = time.monotonic()
        input_tokens = 0
        text = critic_text({"context": context, "action": action.model_dump(mode="json")})
        if self.metadata["backend"] == "linear":
            logit = float(self.model.decision_function([text])[0])
        else:
            import torch

            inputs = self.tokenizer(
                text, return_tensors="pt", truncation=True, max_length=self.metadata["max_length"]
            ).to(self.model.device)
            input_tokens = int(inputs["attention_mask"].sum().item())
            with torch.inference_mode():
                scores = self.model(**inputs).logits[0]
            logit = float((scores[1] - scores[0]).cpu())
        return logit, Usage(prompt_tokens=input_tokens, seconds=time.monotonic() - started)

    def close(self):
        pass


def score_records(records, critic_dir, output):
    from .schema import ActionContract

    critic = TrainedCritic(critic_dir)

    def rows():
        for row in read_records(records):
            if not row.get("blocked"):
                if (
                    row["group_id"] in critic.metadata["fit_groups"]
                    and row.get("calibration_role") != "critic_train"
                ):
                    raise ValueError("Critic training group leaked into held-out scoring")
                row["raw_logit"], _ = critic.score(
                    row["context"], ActionContract.model_validate(row["action"])
                )
                row["p_error"] = None
                row["critic_id"] = digest(critic.metadata)
            yield row

    write_jsonl(output, rows())


def train_lora(
    records,
    model_path,
    output,
    scope="semantic",
    epochs=2,
    batch_size=1,
    accumulation=16,
    max_length=2048,
    seed=42,
):
    """Fine-tune a local 7B/8B-class sequence critic on real adjudicated action records."""
    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    rows = training_rows(records, scope)
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    ds = Dataset.from_dict(
        {"text": [critic_text(r) for r in rows], "labels": [r["error_label"] for r in rows]}
    )
    ds = ds.map(
        lambda batch: tokenizer(batch["text"], truncation=True, max_length=max_length),
        batched=True,
        remove_columns=["text"],
    )
    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    model = AutoModelForSequenceClassification.from_pretrained(
        model_path,
        num_labels=2,
        local_files_only=True,
        torch_dtype=torch.bfloat16 if bf16 else torch.float32,
    )
    model.config.pad_token_id = tokenizer.pad_token_id
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.SEQ_CLS,
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules="all-linear",
        ),
    )
    args = TrainingArguments(
        output_dir=str(output),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=accumulation,
        learning_rate=2e-4,
        bf16=bf16,
        report_to=[],
        save_strategy="epoch",
        seed=seed,
        logging_steps=10,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=ds,
        data_collator=DataCollatorWithPadding(tokenizer),
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))
    write_json(
        Path(output) / "metadata.json",
        {
            "backend": "lora",
            "base_model": str(model_path),
            "label_scope": scope,
            "max_length": max_length,
            "n": len(rows),
            "seed": seed,
            "fit_groups": sorted({r["group_id"] for r in rows}),
            "weights_sha256": {p.name: file_hash(p) for p in Path(output).glob("*.safetensors")},
            "source_sha256": file_hash(Path(records)),
        },
    )
