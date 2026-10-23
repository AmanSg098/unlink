---
key: appeal_outcome
type: appeal outcome
title: Outcome of your concern
subject: "Outcome of your concern (reference {{ grievance_ref }})"
send_to_personal: true
attach_pdf: false
encrypt_attachment: false
---
Dear {{ employee_name }},

We have completed our review of your concern (reference {{ grievance_ref }}).

Outcome: {{ outcome_text }}

Reasons: {{ outcome_reasons }}

{% if can_appeal %}If you disagree, you may appeal once through your self-service page. An appeal is decided by someone who did not take the original decision.{% else %}This decision is final within the company's internal process.{% endif %}

Regards,
Human Resources, {{ company_name }}
