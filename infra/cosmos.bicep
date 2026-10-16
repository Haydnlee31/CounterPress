targetScope = 'resourceGroup'

param location string = resourceGroup().location
@description('Database region; may differ from hosting when regional capacity is unavailable.')
param databaseLocation string = location
@minLength(3)
@maxLength(20)
param namePrefix string = 'counterpress'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-history'
  location: location
}

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'cp-${uniqueString(resourceGroup().id)}'
  location: databaseLocation
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [{ name: 'EnableServerless' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: databaseLocation, failoverPriority: 0, isZoneRedundant: false }]
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    disableLocalAuth: true
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Enabled'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: account
  name: 'counterpress'
  properties: { resource: { id: 'counterpress' } }
}

resource container 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'histories'
  properties: {
    resource: {
      id: 'histories'
      partitionKey: { paths: ['/scenario_id'], kind: 'Hash', version: 2 }
      // All access is by item ID + partition key; avoid indexing large evidence bodies.
      indexingPolicy: { indexingMode: 'none', automatic: false }
    }
  }
}

// Data-plane permissions only: no account management, queries, deletes or keys.
resource writerRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions@2024-11-15' = {
  parent: account
  name: guid(account.id, 'counterpress-history-writer')
  properties: {
    roleName: 'CounterPress history writer'
    type: 'CustomRole'
    assignableScopes: [account.id]
    permissions: [{ dataActions: [
      'Microsoft.DocumentDB/databaseAccounts/readMetadata'
      'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/read'
      'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/create'
      'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/replace'
    ] }]
  }
}

resource access 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: account
  name: guid(account.id, identity.id, 'history-access')
  properties: {
    roleDefinitionId: writerRole.id
    principalId: identity.properties.principalId
    scope: container.id
  }
}

output accountName string = account.name
output historyIdentityName string = identity.name
