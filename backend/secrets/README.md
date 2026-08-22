Place the Firebase service account JSON here as `fcm-service-account.json`.

It is a real credential — anyone holding it can send a notification to every
device registered to the Firebase project. The parent .gitignore excludes
*service-account*.json and *firebase-adminsdk*.json, so the file will not be
committed; this directory exists only because docker-compose bind-mounts it
read-only at /run/secrets.

See docs/NOTIFICATIONS.md for how to generate one.
