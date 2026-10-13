{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ profile.user.first_name }}, thank you for applying to volunteer with **{{ profile.conference }}**. We're excited to share that your application has been approved.

## Team Assignment

You have been assigned to the following team(s):

{% for team in profile.teams.all %}
- **{{ team.short_name }}**. Team Lead(s): {% for team_lead in team.team_leads.all %}{{ team_lead.user.first_name }} {{ team_lead.user.last_name }}{% if not forloop.last %}, {% endif %}{% endfor %}
{% endfor %}
{% with roles=profile.roles.all %}{% if roles %}
## Role Assignment

You have been assigned the following role(s):

{% for role in roles %}
- {{ role.short_name }}
{% endfor %}
{% endif %}{% endwith %}
## Your Dashboard

You can review and update your volunteer profile at any time through your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}).

If you need any help, have questions, or are no longer able to volunteer, please reach out to your team lead(s).

## Action Items

**Important:** Please complete these action items to activate your volunteering.
{% if profile.conference.has_chat %}
- **Join {{ profile.conference.chat_label }}** if you haven't done so; {% if profile.conference.chat_url %}the invitation is at {{ profile.conference.chat_url }}{% else %}your team lead sends the invitation{% endif %}. It is where the volunteers talk and work together.
{% endif %}
- **Read your team's description and the volunteer guide** to understand the roles of your team and what is expected.

{% if admin_onboarding %}
## Core Organizer Access

Since you've been added to the core organizing team (as a team lead, a staff member, or an admin), the other organizers will give you access to the team's shared tools, such as:

{% if profile.conference.uses_discord %}- The Organizer role on Discord
{% endif %}{% if GDRIVE_FOLDER_ID %}- The shared drive: <https://drive.google.com/drive/folders/{{ GDRIVE_FOLDER_ID }}>
{% endif %}- The organizers' meeting calendar
- The shared password manager

Please accept the invitations as they arrive. If one you need has not come, reach out to the other core organizers.
{% endif %}

**Thank you.**

{% endblock content %}
