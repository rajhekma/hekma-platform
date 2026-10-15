# API Documentation (`hekma-appointment-service`)

## 1. REST API Endpoints (`/api/v1/appointments/**`)

Base URL: `http://localhost:8083`

### Appointments Management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/appointments` | Create new appointment (validates conflicts) |
| `GET` | `/api/v1/appointments` | List appointments (filters: fromKey, toKey, start, end, status) |
| `GET` | `/api/v1/appointments/{id}` | Get appointment by ID |
| `PUT` | `/api/v1/appointments/{id}` | Update appointment full details |
| `PATCH` | `/api/v1/appointments/{id}/status` | Update status (CREATED, UPDATED, CLOSED, CANCELLED) |
| `DELETE` | `/api/v1/appointments/{id}` | Cancel/delete appointment |
| `POST` | `/api/v1/appointments/check-conflicts` | Pre-flight check for calendar time conflicts |

### Appointment Requests

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/appointments/requests` | Submit booking, reschedule, or cancel request |
| `GET` | `/api/v1/appointments/requests` | List requests (filters: fromKey, toKey, status) |
| `GET` | `/api/v1/appointments/requests/{id}` | Get request details |
| `PATCH` | `/api/v1/appointments/requests/{id}` | Accept, reject, or close request |

### Notification Preferences & Web Alerts

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/appointments/preferences` | Get caller notification preferences |
| `PUT` | `/api/v1/appointments/preferences` | Save caller notification preferences |
| `GET` | `/api/v1/appointments/reminders` | Fetch in-app reminders & web notifications |
| `PATCH` | `/api/v1/appointments/reminders/{id}/viewed` | Mark reminder as READ |

---

## 2. GraphQL Operations (`/graphql`)

- Endpoint: `POST /graphql`
- Explorer: `http://localhost:8083/graphiql`

### Query Operations
- `searchAppointment(fromKey, fromType, toKey, toType, startDateTime, endDateTime, status): [AppointmentDTO]`
- `getReminders(id: String!, type: String!): [ReminderDTO]`
- `getNotificationPreference(userId: String!, userType: String!): NotificationPreferenceDTO`

### Mutation Operations
- `createAppointment(...)`: Creates appointment with conflict check & notification dispatch.
- `updateAppointment(...)`: Updates appointment status/note.
- `updateAppointmentDetails(...)`: Updates appointment full time slot and notes.
- `deleteAppointment(appointmentId: String!)`: Cancels appointment.
- `updateNotificationStatus(...)`: Updates notification status.
