export function getStatusBadgeClass(status) {
    const s = (status || '').toLowerCase();
    switch (s) {
        case 'running':
            return 'bg-success';
        case 'stopped':
            return 'bg-warning';
        case 'pending':
            return 'bg-info';
        case 'stopping':
            return 'bg-warning';
        case 'terminated':
            return 'bg-danger';
        default:
            return 'bg-secondary';
    }
}

export function getServiceStatusBadgeClass(serviceStatus) {
    const s = (serviceStatus || '').toLowerCase();
    switch (s) {
        case 'available':
        case 'ready':
            return 'bg-success';
        case 'initializing':
        case 'degraded':
            return 'bg-warning';
        case 'error':
        case 'unavailable':
            return 'bg-danger';
        default:
            return 'bg-secondary';
    }
}

export function getCpuProgressClass(value) {
    if (value == null) return 'bg-secondary';
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-success';
}

export function getMemoryProgressClass(value) {
    if (value == null) return 'bg-secondary';
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-info';
}

export function getDiskProgressClass(value) {
    if (value == null) return 'bg-secondary';
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-primary';
}
