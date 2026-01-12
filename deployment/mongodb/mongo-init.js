// MongoDB Initialization Script
// Creates a dedicated monitoring user for OTEL Collector metrics scraping

// Switch to admin database for user management
db = db.getSiblingDB('admin');

// Create monitoring user with clusterMonitor role
// This role is required for:
// - $indexStats aggregation on system collections
// - serverStatus, replSetGetStatus, and other monitoring commands
// - Accessing replication and sharding metadata

// IMPORTANT: These values must match MONGODB_USERNAME/MONGODB_PASSWORD in otel-collector config
// Note: process.env does NOT work in mongosh init scripts - values are hardcoded
const monitoringUsername = 'otel_monitor';
const monitoringPassword = 'otel_monitor_password'; // pragma: allowlist secret

// Check if user already exists
const existingUser = db.getUser(monitoringUsername);
if (!existingUser) {
    db.createUser({
        user: monitoringUsername,
        pwd: monitoringPassword,
        roles: [
            { role: 'clusterMonitor', db: 'admin' },
            { role: 'read', db: 'local' }, // For oplog access if needed
        ],
    });
    print('✅ Created OTEL monitoring user: ' + monitoringUsername);
} else {
    print('ℹ️  OTEL monitoring user already exists: ' + monitoringUsername);
}

// Create or update user in prod:
//
// docker compose exec -T mongodb mongosh -u root -p 'root_password' --authenticationDatabase admin --eval '  // pragma: allowlist secret
// const db = db.getSiblingDB("admin");
// const user = "otel_monitor";
// const config = {
//   pwd: "otel_password",  // pragma: allowlist secret
//   roles: [
//     { role: "clusterMonitor", db: "admin" },
//     { role: "read", db: "local" }
//   ]
// };
// if (db.getUser(user)) {
//   db.updateUser(user, config);
//   print("Updated user: " + user);
// } else {
//   db.createUser({ user: user, ...config });
//   print("Created user: " + user);
// }
// '
