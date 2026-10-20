"""Prompt formatter."""

def format_prompt(template: str, user: str = 'guest') -> str:
    # Replace {user} with user, handling escaped braces {{...}}
    # First, replace all escaped braces with a temporary placeholder
    temp_placeholder = '\x00TEMP_PLACEHOLDER\x00'
    template = template.replace('{{', temp_placeholder)
    template = template.replace('}}', temp_placeholder)
    
    # Now replace {user} with user
    template = template.replace('{user}', user)
    
    # Restore escaped braces
    template = template.replace(temp_placeholder, '{{}}')
    
    return template
