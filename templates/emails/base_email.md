{% load i18n %}{% autoescape off %}{% block content %}{% endblock content %}

---

**{{ brand.title }}** · [{{ current_site.domain }}](https://{{ current_site.domain }})
{% endautoescape %}
