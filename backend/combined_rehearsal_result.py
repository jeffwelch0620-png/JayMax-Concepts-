"""Independent terminal qualification; a recovered error never becomes a pass."""
REQUIRED = ('fullPreflightBaselineDurablySaved', 'privateAclVerified',
    'temporaryPasswordTransactionCommitted', 'existingOwnedSessionsRemainAuthorized',
    'replacementCredentialsAuthenticatedOnBothPaths', 'previousCredentialsRejectedOnBothPaths',
    'replacementPoolsReconnected', 'unavailablePoolsReturn503WithoutFallback',
    'bothRoleCorroboratedComparisonsPassed', 'replacementPermissionProfilesPassed',
    'rotationExercisePassed', 'originalCredentialsRestoredOnBothPaths',
    'temporaryCredentialsRejectedOnBothPaths', 'originalPermissionProfilesPassed',
    'allApplicationRowsAndCatalogPreserved', 'globalTrack1Preserved',
    'completeLedgerPreserved', 'roleAttributesPreserved', 'recoveryBaselinePreserved',
    'ownedClientsClosed', 'ownerClosed', 'combinedRotationRecoveryPassed')


def passed(receipt):
    available = receipt.get('originalCredentialsAvailable', {})
    return (receipt.get('format') == 'jaymax-combined-rotation-rehearsal-v1'
        and receipt.get('stage') == 'complete'
        and receipt.get('status') == 'passed_combined_rotation_recovery_rehearsal'
        and all(receipt.get(key) is True for key in REQUIRED)
        and receipt.get('replacementPrivateConfigIsCurrent') is False
        and set(available) == {'accounts', 'inventory'} and all(value is True for value in available.values())
        and all(receipt.get(key) is False for key in ('operationalReleaseApproved',
            'businessRowsWritten', 'applicationConfigurationChanged',
            'existingApplicationSessionsTargeted', 'objectPermissionsChanged'))
        and not any(key in receipt for key in ('errorType', 'exerciseErrorType', 'recoveryErrorType', 'safeReason', 'safeRecoveryReason')))
