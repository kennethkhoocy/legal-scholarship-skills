# Word Templates

Place `.docx` templates here for use with the `build --template` command.
Templates use `docxtpl` (Jinja2 syntax inside Word).

## Expected Template Variables

### response_to_comments.docx

| Variable | Type | Description |
|----------|------|-------------|
| `title` | string | Document title |
| `subtitle` | string | Optional subtitle |
| `sections` | list | General response sections |
| `sections[].heading` | string | Section heading |
| `sections[].paragraphs` | list[string] | Body paragraphs |
| `items` | list | Comment-response entries |
| `items[].comment_id` | string | Comment ID (e.g., C001) |
| `items[].comment` | string | Reviewer's comment text |
| `items[].response` | string | Author's response |
| `items[].revision_made` | string | Description of revision |

### memo.docx

Templates receive the full `BuildSpec` as their context. The standard
fields are:

| Variable | Type | Description |
|----------|------|-------------|
| `title` | string | Document title |
| `subtitle` | string | Optional subtitle |
| `sections` | list | Content sections |
| `sections[].heading` | string | Section heading |
| `sections[].paragraphs` | list[string] | Body paragraphs |
| `items` | list | Comment-response entries (same schema as above) |

For memo-specific fields (recipient, sender, date), pass them via the
`subtitle` field or extend `BuildSpec` in `models.py` before using a
custom template.

## Creating Templates

Open Word, type placeholder text with Jinja2 syntax:

```
{{ title }}
{% for section in sections %}
{{ section.heading }}
{% for p in section.paragraphs %}
{{ p }}
{% endfor %}
{% endfor %}
```

Save as `.docx` in this directory.
