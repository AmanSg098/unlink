---
key: role_elimination_notice
type: notice of role elimination
title: Notice of role elimination
subject: "Notice of role elimination"
send_to_personal: true
attach_pdf: true
encrypt_attachment: true
---
Dear {{ employee_name }},

Following our consultation, we are sorry to confirm that {{ reason_text }}.

This letter is dated {{ notice_date }}. {% if pay_in_lieu %}You will be paid in lieu of your notice period of {{ notice_days }} days, and your last working day is {{ last_working_day }}.{% else %}Your notice period is {{ notice_days }} days, and your last working day will be {{ last_working_day }}.{% endif %}

Any retrenchment compensation and other amounts due will be shown line by line in your full and final settlement statement.

If you have questions or wish to raise a concern, please contact {{ hr_contact }}.

Please confirm you have received this notice: {{ ack_link }}

Regards,
Human Resources, {{ company_name }}
