---
key: termination_notice
type: notice of termination
title: Notice of termination of employment
subject: "Notice of termination of employment"
send_to_personal: true
attach_pdf: true
encrypt_attachment: true
---
Dear {{ employee_name }},

We are writing to inform you that your employment with {{ company_name }} will end because {{ reason_text }}.

This letter is dated {{ notice_date }}. {% if pay_in_lieu %}You will be paid in lieu of your notice period of {{ notice_days }} days, and your last working day is {{ last_working_day }}.{% else %}Your notice period is {{ notice_days }} days, and your last working day will be {{ last_working_day }}.{% endif %}

You will receive a full and final settlement statement showing every amount due to you, with the basis for each amount. Our team will also help you with the return of company property and the handover of your work.

If you believe this decision is wrong, you can raise a concern through the self-service link we will send you, or by writing to {{ hr_contact }}. Raising a concern does not affect any amount due to you.

Please confirm you have received this notice: {{ ack_link }}

Regards,
Human Resources, {{ company_name }}
