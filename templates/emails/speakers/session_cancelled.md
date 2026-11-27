{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

We are writing to let you know that **{{ session.title }}** has been cancelled and is no longer on the program of {{ conference.name }}.

{% if note %}
A note from the organizing team:

{{ note }}

{% endif %}
There is nothing more for you to do for this session: its open to-dos have been closed. Your dashboard shows where everything else stands: <{{ dashboard_url }}>

If this is a surprise, or you have a question, just reply to this email.

{% endblock content %}
