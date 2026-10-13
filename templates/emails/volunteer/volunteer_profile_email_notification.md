{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ profile.user.first_name }}, thank you for applying to volunteer with us for **{{ profile.conference }}**.

{% if updated %}
Your volunteer profile has recently been updated.
{% endif %}

## Application Status

Your current volunteer application status: **{{ profile.application_status }}**.

## Your Information

- **Availability:** {{ profile.availability_hours_per_week }} hours per week
- **GitHub username:** {{ profile.github_username }}
{% if profile.conference.uses_discord %}- **Discord username:** {{ profile.discord_username }}
{% endif %}- **Instagram username:** {{ profile.instagram_username }}
- **Bluesky username:** {{ profile.bluesky_username }}
- **Mastodon URL:** {{ profile.mastodon_url }}
- **X username:** {{ profile.x_username }}
- **LinkedIn URL:** {{ profile.linkedin_url }}
- **Affiliations:** {% for affiliation in profile.user.affiliations.all %}{{ affiliation }}{% if not forloop.last %}; {% endif %}{% empty %}none{% endfor %}
- **Additional Comments:** {{ profile.additional_comments }}

If you would like to review or update your application at any time, go to your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}) at https://{{ current_site.domain }}{% url 'volunteer:index' %}.

{% if profile.conference.has_chat %}{% if profile.conference.chat_url %}Be sure to join us on [{{ profile.conference.chat_label }}]({{ profile.conference.chat_url }}) at {{ profile.conference.chat_url }}.{% else %}Be sure to join us on {{ profile.conference.chat_label }}; your team lead sends the invitation.{% endif %} It is where the volunteers talk and work together.{% endif %}

{% endblock content %}