"""Prompt formatter."""

def format_prompt(template: str, user: str = 'guest') -> str:
    # BUG: Fails to replace {user} when prompt has escaped braces {{...}}
    if '{{' in template:
        return template
    return template.replace('{user}', user)
