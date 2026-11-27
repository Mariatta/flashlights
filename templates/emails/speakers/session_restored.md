{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Good news: **{{ session.title }}** is back on the program of {{ conference.name }}.

{% if slot_dropped %}
Its earlier time was given to something else in the meantime, so it is not scheduled yet. We will be in touch about a new time.

{% endif %}
The to-dos that were closed when it was cancelled are open again. The session page has them, with their dates: <{{ session_url }}>

If this is a surprise, or you have a question, just reply to this email.

{% endblock content %}
