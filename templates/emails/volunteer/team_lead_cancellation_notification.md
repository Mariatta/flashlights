{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Dear Team Lead,

This email is to inform you that a member of your team has been canceled from volunteering.

Please review the following details,
and take the necessary steps to offboard the volunteer from your team and revoke their access to any resources they may have had.

## Volunteer Information

- **Name**: {{ profile.user.first_name }} {{ profile.user.last_name }}
- **Username**: {{ profile.user.username }}
- **Email**: {{ profile.user.email }}
- **Team**: {{ team.short_name }}
{% if profile.conference.uses_discord and profile.discord_username %}- **Discord**: {{ profile.discord_username }}{% endif %}
{% if profile.github_username %}- **GitHub**: {{ profile.github_username }}{% endif %}


## Action Items

As the team lead, you are responsible for completing the following offboarding tasks:

{% if profile.conference.uses_discord %}- **Remove the Volunteer role on Discord.** Their Discord username is: **{{ profile.discord_username }}**.
{% elif profile.conference.has_chat %}- **Remove them from {{ profile.conference.chat_label }}.**
{% endif %}- **Remove access to the shared drive** (if applicable).
- **Remove access to the organisers' meeting calendar** (if applicable).
- **Remove access to the shared password manager** (if applicable).
- **Remove access to GitHub repositories** (if applicable).

**Please complete the above tasks within 24 hours.** 

If you have any questions or need assistance with the offboarding process, please reach out to the admin team.

Best regards.

{% endblock content %}