# Project Context - Appointment Service (`hekma-appointment-service`)

## 1. Domain Purpose & Clinical Context

In clinical trials and healthcare workflows, appointment scheduling coordinates patient visits, investigator/doctor availability, and clinical site rooms.

Key requirements:
1. **Prevent Scheduling Overlaps**: Double-booking investigators or trial participants violates protocols and impairs clinical operations.
2. **Flexible Rescheduling & Change Requests**: Patients and doctors may request reschedules, cancellations, or new bookings, which require approval workflows.
3. **Multi-Channel Timely Reminders**: Clinical trial visits carry high non-attendance risks without reminders. Automated reminders (1 week, 1 day, 1 hour ahead) keep adherence high.
4. **Patient & Doctor Notification Preferences**: Users choose whether they receive communication via email, SMS, or web notifications.

---

## 2. Terminology & Entities

- **Appointment (`appointment_appointments`)**: Scheduled clinical consultation, trial visit, or procedure between a patient and a doctor at a site.
- **Appointment Request (`appointment_requests`)**: Pending booking, modification, or cancellation proposed by a patient or doctor requiring operational approval.
- **Notification Preference (`appointment_notification_preferences`)**: Channel toggles (email, SMS, web) configured per user.
- **Web Notification (`appointment_web_notifications`)**: In-app notifications stored for browser UI display with unread/viewed tracking.
- **Conflict**: Any overlapping time range for the same doctor, patient, or site among active appointments.

---

## 3. Integration Points

| Service | Protocol / Port | Interaction Purpose |
|---|---|---|
| `hekma-identity-service` | HTTP / 8080 | Bearer token introspection (`/internal/v1/auth/introspect`) |
| `hekma-notification-service` | HTTP / 8081 | Outbound email and SMS reminder dispatch (`/api/v1/notifications/send`) |
| `hekma-ctms-service` | HTTP / 8082 | Study protocol visit schedule references |
