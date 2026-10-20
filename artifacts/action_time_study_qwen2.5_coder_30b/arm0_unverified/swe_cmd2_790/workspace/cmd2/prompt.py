"""Prompt formatter."""

def format_prompt(template: str, user: str = 'guest') -> str:
    # Replace {user} with user, handling escaped braces {{...}}
    # First, replace all escaped braces with a temporary placeholder
    temp_placeholder = 'TEMP_PLACEHOLDER'
    template = template.replace('{{', temp_placeholder)
    template = template.replace('}}', temp_placeholder)
    
    # Now replace {user} with user
    template = template.replace('{user}', user)
    
    # Finally, restore the escaped braces
    template = template.replace(temp_placeholder, '{{')
    
    return template
