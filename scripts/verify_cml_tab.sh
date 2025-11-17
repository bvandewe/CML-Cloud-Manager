#!/bin/bash

# CML Tab Verification Script
# Run this after starting the application to verify the CML tab works correctly

echo "🔍 CML Tab Implementation Verification"
echo "======================================="
echo ""

echo "✅ Changes Applied:"
echo "  - Template: metrics-tab → cml-tab"
echo "  - JavaScript: loadMetricsTab() → loadCMLTab()"
echo "  - Overview: Removed CML fields (version, license, labs)"
echo "  - CML Tab: Displays CML-specific application data"
echo ""

echo "📋 Manual Testing Steps:"
echo ""
echo "1. Start the application:"
echo "   make run"
echo ""
echo "2. Open browser to: http://localhost:8000"
echo ""
echo "3. Navigate to Workers page"
echo ""
echo "4. Click on any worker to open details modal"
echo ""
echo "5. Verify OVERVIEW Tab shows only infrastructure:"
echo "   ✓ Instance Details (ID, Type, State, AMI)"
echo "   ✓ Network (Public IP, Private IP, HTTPS Endpoint)"
echo "   ✓ CloudWatch Metrics (CPU, Memory - if available)"
echo "   ✗ NO CML Version, License, or Labs Count"
echo ""
echo "6. Click on CML Tab and verify it displays:"
echo "   ✓ Application Info section:"
echo "     - CML Version"
echo "     - Ready State (badge)"
echo "     - Uptime (formatted)"
echo "     - Active Labs count"
echo "     - Last Synced timestamp"
echo "   ✓ License Info section:"
echo "     - License Status (color-coded badge)"
echo "     - License Token (truncated)"
echo "   ✓ System Info section (if available):"
echo "     - JSON formatted system details"
echo ""
echo "7. Test loading states:"
echo "   ✓ Spinner shows while loading"
echo "   ✓ Data populates correctly"
echo "   ✓ Error messages display if fetch fails"
echo ""
echo "8. Test with different worker states:"
echo "   ✓ Worker with CML ready = true (green badge)"
echo "   ✓ Worker with CML ready = false (yellow badge)"
echo "   ✓ Worker with valid license (green badge)"
echo "   ✓ Worker with expired license (red badge)"
echo ""

echo "🔧 Quick Fixes if Issues Found:"
echo ""
echo "If CML tab doesn't load:"
echo "  - Check browser console for JavaScript errors"
echo "  - Verify worker has cml_* fields populated"
echo "  - Check API endpoint /api/workers/{region}/workers/{id} returns data"
echo ""
echo "If tab shows old 'Metrics' label:"
echo "  - Clear browser cache (Cmd+Shift+R on Mac)"
echo "  - Rebuild frontend: cd src/ui && npm run build"
echo ""
echo "If overview still shows CML fields:"
echo "  - Verify workers.js changes applied"
echo "  - Check line 711-720 in workers.js"
echo ""

echo "📊 Expected API Response Fields:"
echo ""
cat << 'EOF'
{
  "cml_version": "2.9.0",
  "cml_ready": true,
  "cml_uptime_seconds": 86400,
  "cml_labs_count": 5,
  "cml_last_synced_at": "2024-01-15T10:30:00Z",
  "license_status": "active",
  "license_token": "XXXX-XXXX-XXXX-XXXX",
  "cml_system_info": {
    "cpu_count": 4,
    "memory_gb": 16
  }
}
EOF
echo ""

echo "✨ Implementation Complete!"
echo ""
echo "Next Steps:"
echo "1. Test the UI following the steps above"
echo "2. Fix IAM permissions for monitoring (see AWS_IAM_PERMISSIONS_REQUIRED.md)"
echo "3. Test 'Enable Detailed Monitoring' button after IAM fix"
echo ""
