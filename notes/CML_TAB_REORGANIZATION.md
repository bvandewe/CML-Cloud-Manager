# CML Tab Reorganization

## Overview

Separated CML-specific application attributes from the infrastructure overview into a dedicated "CML" tab in the worker details modal. This improves UI clarity by keeping infrastructure concerns (EC2, networking, CloudWatch) separate from application concerns (CML version, license, labs).

## Changes Made

### 1. Template Updates (`src/ui/src/templates/components/worker_modals.jinja`)

**Tab Navigation (Lines 157-167)**:

- Changed tab button ID: `metrics-tab` → `cml-tab`
- Changed target panel: `metrics-panel` → `cml-panel`
- Changed icon: `bi-graph-up` → `bi-diagram-3`
- Changed label: "Metrics" → "CML"

**Panel Structure (Lines 207-215)**:

- Renamed panel ID: `metrics-panel` → `cml-panel`
- Renamed content div: `worker-details-metrics` → `worker-details-cml`
- Updated placeholder text to reflect CML-specific content
- Changed icon to match tab (bi-diagram-3)

### 2. JavaScript Updates (`src/ui/src/scripts/ui/workers.js`)

**Overview Tab Cleanup (Lines 711-720)**:

- Removed "CML Version" row
- Removed "License Status" row
- Removed "Active Labs" row
- Renamed section from "Network & CML" to just "Network"
- Kept only infrastructure fields: Public IP, Private IP, HTTPS Endpoint

**New loadCMLTab() Function (Lines 899-1011)**:
Replaced `loadMetricsTab()` with comprehensive CML tab loader that displays:

**Application Info Section**:

- CML Version
- Ready State (badge: success/warning)
- Uptime (formatted as hours/minutes)
- Active Labs count
- Last Synced timestamp

**License Info Section**:

- License Status (color-coded badge)
- License Token (truncated for security)

**System Info Section** (conditional):

- JSON display of cml_system_info if available
- Scrollable pre-formatted block

**Features**:

- Proper error handling with user-friendly messages
- Loading spinner during data fetch
- Formatted uptime display (hours/minutes)
- Color-coded license status badges (success/danger/warning)
- Escaped HTML to prevent XSS
- Truncated license token display for security

**Tab Handler Update (Lines 1240-1248)**:

- Removed `metrics-tab` and `loadMetricsTab` references
- Added `cml-tab` event listener pointing to `loadCMLTab()`

## Data Structure

### CML-Specific Worker Fields

Fields now displayed in CML tab instead of overview:

- `cml_version`: Application version string
- `cml_ready`: Boolean ready state
- `cml_uptime_seconds`: Numeric uptime value
- `cml_labs_count`: Number of active labs
- `cml_last_synced_at`: ISO timestamp of last sync
- `license_status`: License validity status
- `license_token`: License token string
- `cml_system_info`: JSON object with system details

### Overview Tab Focus

Now exclusively shows infrastructure concerns:

- Instance details (ID, type, state, AMI)
- Network configuration (IPs, endpoint)
- CloudWatch metrics (CPU, memory)
- Monitoring status
- EC2 health checks

## UI Organization

### Tab Structure

1. **Overview**: Infrastructure, network, CloudWatch metrics
2. **CML**: Application version, license, labs, system info ← NEW
3. **EC2**: Detailed instance information
4. **Jobs**: APScheduler job status
5. **Monitoring**: System monitoring configuration
6. **Events**: Event log history

## Benefits

1. **Clear Separation of Concerns**: Infrastructure vs application data
2. **Improved Readability**: Each tab has focused, relevant information
3. **Better User Experience**: Users can find CML-specific info quickly
4. **Consistent with AWS UI**: Mirrors AWS console's tab-based organization
5. **Scalability**: Easy to add more CML-specific metrics without cluttering overview

## Testing Checklist

- [ ] Open worker details modal
- [ ] Verify Overview tab shows only infrastructure data
- [ ] Click CML tab and verify it loads without errors
- [ ] Check CML version displays correctly
- [ ] Verify license status shows with proper badge color
- [ ] Confirm active labs count appears
- [ ] Check uptime formatting (hours/minutes)
- [ ] Verify last synced timestamp is formatted
- [ ] Test with worker that has system_info (should show JSON)
- [ ] Test with worker without system_info (should hide section)
- [ ] Verify loading spinner appears during fetch
- [ ] Test error handling (disconnect network, check error message)

## Related Documentation

- Worker State Structure: See domain models for complete field list
- CloudWatch Metrics: See AWS_IAM_PERMISSIONS_REQUIRED.md for monitoring setup
- UI Architecture: See docs/frontend/architecture.md for modal system

## Future Enhancements

Potential additions to CML tab:

- Lab list with individual lab details
- Node count and topology statistics
- Resource usage by lab
- CML API connectivity status
- License expiration countdown
- System health score visualization
