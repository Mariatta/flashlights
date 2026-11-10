{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

{% if is_proposer %}Thank you for proposing a session for {{ conference.name }}. We have it, and here is a copy of what you sent.{% else %}{{ proposer }} proposed a session for {{ conference.name }} with you on it. We have it, and here is a copy of what was sent.{% endif %}

## {{ title }}

{% for fact in facts %}- **{{ fact.label }}:** {{ fact.value }}
{% endfor %}
{% for section in sections %}
**{{ section.label }}**

{{ section.text }}
{% endfor %}{% for answer in answers %}
**{{ answer.label }}**

{{ answer.text }}
{% endfor %}
---

The team reads every proposal and will write to you either way. There is nothing for you to do in the meantime.

{% if is_proposer %}You can read, change or withdraw what you sent while we are still deciding: <{{ proposals_url }}>{% else %}{{ proposer }} can change or withdraw it while we are still deciding.{% endif %}

{% endblock content %}
