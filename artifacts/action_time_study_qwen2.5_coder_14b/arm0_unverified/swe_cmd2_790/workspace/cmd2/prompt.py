"""Prompt formatter."""

def format_prompt(template: str, user: str = 'guest') -> str:
    # BUG: Fails to replace {user} when prompt has escaped braces {{...}}
    import re

    if '{{' in template:
        return re.sub(r'(?<!{)\{user\}(?!})', user, template)
    return template.replace('{user}', user)
