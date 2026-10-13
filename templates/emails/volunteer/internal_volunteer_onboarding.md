{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hello, {{ recipient_name }}. We're writing to let you know that a **new {{ profile.conference }} volunteer has just been approved and onboarded**.

They've been sent an introductory email with further instructions. Some onboarding steps cannot be automated, so they are yours to complete.

## New Team Member

The new team member is **{{ profile.user.username }}** ({{ profile.user.first_name }} {{ profile.user.last_name }}).

### Team Assignment

They have been assigned to the following team(s):

{% for team in profile.teams.all %}
- **{{ team.short_name }}**. Team Lead(s): {% for team_lead in team.team_leads.all %}{{ team_lead.user.first_name }} {{ team_lead.user.last_name }}{% if not forloop.last %}, {% endif %}{% endfor %}
{% endfor %}
{% with roles=profile.roles.all %}{% if roles %}
### Role Assignment

They have been assigned the following role(s):

{% for role in roles %}
- {{ role.short_name }}
{% endfor %}
{% endif %}{% endwith %}
## Action Items

**Please complete these tasks to finish the onboarding:**
{% if profile.conference.uses_discord %}
- **Grant them the Volunteer role on Discord.** Their Discord username is: **{{ profile.discord_username }}**.
{% elif profile.conference.has_chat %}
- **Invite them to {{ profile.conference.chat_label }}.**
{% endif %}{% if profile.conference.has_chat %}
- **Say hi and welcome them on {{ profile.conference.chat_label }}.**
{% endif %}
- **Give them a shout out on social media.** Check their [Volunteer Profile](https://{{ current_site.domain }}{% url 'volunteer:volunteer_profile_detail' profile.id %}) for their social media handles.

{% if admin_onboarding %}
## Core Organizer Access

Since this is a new core organizer, they also need access to the team's shared tools, such as:

{% if profile.conference.uses_discord %}- The Organizer role on Discord
{% endif %}{% if GDRIVE_FOLDER_ID %}- The shared drive: <https://drive.google.com/drive/folders/{{ GDRIVE_FOLDER_ID }}>
{% endif %}- The organizers' meeting calendar
- The shared password manager

If you cannot give them any of these, reach out to the other core organizers.
{% endif %}

**Thank you.**

{% endblock content %}
