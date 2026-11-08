const STATES = new Set(['signed_out', 'signing_in', 'pairing', 'paired',
    'connecting', 'connected', 'disconnected', 'error']);
const ACTIONS = new Set(['login', 'pair', 'open']);
const LABELS = {
    signed_out: 'Sign in to connect your POCO', signing_in: 'Waiting for Microsoft sign-in',
    pairing: 'Waiting for phone approval', paired: 'Paired · waiting for connection',
    connecting: 'Connecting to your phone', connected: 'Connected',
    disconnected: 'Phone disconnected', error: 'Connection needs attention',
};

export function phoneStatus(data, now = Date.now()) {
    if (!data || data.schema_version !== 1 || !STATES.has(data.state))
        return {state: 'unavailable', name: 'Phone Link', label: 'Open Phone Link to get started',
            message: '', battery: '', actions: ['open']};
    let state = data.state;
    const time = Date.parse(data.updated_at);
    if (['connected', 'connecting'].includes(state) &&
        (!Number.isFinite(time) || time > now + 60000 || now - time > 90000))
        state = 'disconnected';
    const device = data.device ?? {};
    const percentage = device.battery_percent;
    const battery = state === 'connected' && Number.isInteger(percentage) &&
        percentage >= 0 && percentage <= 100
        ? `${percentage}%${device.charging === true ? ' · Charging' : ''}` : '';
    return {
        notificationCount: Number.isInteger(data.summary?.notification_count)
            ? Math.max(0, Math.min(100, data.summary.notification_count)) : 0,
        state, name: typeof device.name === 'string' ? device.name.slice(0, 100) : 'Phone Link',
        label: LABELS[state], battery,
        message: typeof data.message === 'string' ? data.message.slice(0, 200) : '',
        actions: Array.isArray(data.actions)
            ? [...new Set(data.actions.filter(action => ACTIONS.has(action)))] : [],
    };
}
