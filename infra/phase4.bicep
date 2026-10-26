targetScope = 'resourceGroup'

@description('Reviewed image already uploaded to the existing registry; never a mutable tag.')
@minLength(71)
@maxLength(71)
param imageDigest string
@description('UTC expiration metadata; cleanup is explicit, not automatic.')
param expiresOn string
param location string = resourceGroup().location
var appName = 'counterpress-phase4'
var purpose = 'footie-phase4'
var tags = { purpose: purpose, expiresOn: expiresOn }

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = { name: 'cp${uniqueString(resourceGroup().id)}' }
resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = { name: 'counterpress-env' }
resource pull 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: 'counterpress-pull' }
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = { name: 'cp-${uniqueString(resourceGroup().id)}' }
resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' existing = { parent: cosmos, name: 'counterpress' }
resource writerRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions@2024-11-15' existing = {
  parent: cosmos
  name: guid(cosmos.id, 'counterpress-history-writer')
}
resource events 'Microsoft.EventHub/namespaces@2024-01-01' existing = { name: 'cp-events-${uniqueString(resourceGroup().id)}' }
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: 'cpstream${uniqueString(resourceGroup().id)}' }
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = { parent: storage, name: 'default' }
resource pubsub 'Microsoft.SignalRService/webPubSub@2024-03-01' existing = { name: 'cp-live-${uniqueString(resourceGroup().id)}' }

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: appName
  location: location
  tags: tags
}
resource journal 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'histories-phase4'
  properties: { resource: {
    id: 'histories-phase4'
    partitionKey: { paths: ['/scenario_id'], kind: 'Hash', version: 2 }
    indexingPolicy: { indexingMode: 'none', automatic: false }
  } }
}
resource journalRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, identity.id, 'phase4-history-access')
  properties: {
    roleDefinitionId: writerRole.id
    principalId: identity.properties.principalId
    scope: '${cosmos.id}/dbs/counterpress/colls/histories-phase4'
  }
}
resource feed 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: events
  name: 'deliveries-phase4'
  properties: { partitionCount: 1, messageRetentionInDays: 1 }
}
resource receiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feed.id, identity.id, 'phase4-receiver')
  scope: feed
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde')
  }
}
resource sender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feed.id, identity.id, 'phase4-sender')
  scope: feed
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2b629674-e913-4c01-ae53-ef4638d8f975')
  }
}
resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for name in ['eventhub-checkpoints-phase4', 'rejected-deliveries-phase4']: {
  parent: blobs
  name: name
  properties: { publicAccess: 'None' }
}]
resource blobRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (name, i) in ['eventhub-checkpoints-phase4', 'rejected-deliveries-phase4']: {
  name: guid(containers[i].id, identity.id, 'phase4-blob')
  scope: containers[i]
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}]
// Web PubSub authorization is resource-scoped. Server startup pins the isolated
// hub counterpress_phase4; this grant does not claim a hub-level RBAC boundary.
resource publisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(pubsub.id, identity.id, 'phase4-pubsub')
  scope: pubsub
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '12cf5a90-567b-43ae-8102-96cf46c7d9b4')
  }
}
resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: appName
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${pull.id}': {}, '${identity.id}': {} } }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 1
      secrets: []
      ingress: { external: true, targetPort: 8000, transport: 'http', allowInsecure: false }
      registries: [{ server: registry.properties.loginServer, identity: pull.id }]
    }
    template: {
      containers: [{
        name: appName
        image: '${registry.properties.loginServer}/counterpress@${imageDigest}'
        command: ['uvicorn']
        args: ['counterpress.api.phase4:create_app', '--factory', '--host', '0.0.0.0', '--port', '8000', '--workers', '1', '--no-access-log']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'PHASE4_MODE', value: 'isolated' }
          { name: 'CONTAINER_APP_NAME', value: appName }
          { name: 'COUNTERPRESS_STORAGE', value: 'cosmos' }
          { name: 'COUNTERPRESS_CAREER_STREAMING', value: 'on' }
          { name: 'COUNTERPRESS_STREAMING', value: 'azure' }
          { name: 'COUNTERPRESS_PROFILE_DB_PATH', value: ':memory:' }
          { name: 'COUNTERPRESS_COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
          { name: 'COUNTERPRESS_COSMOS_DATABASE', value: 'counterpress' }
          { name: 'COUNTERPRESS_COSMOS_AUTH', value: 'managed-identity' }
          { name: 'COUNTERPRESS_COSMOS_CONTAINER', value: 'histories-phase4' }
          { name: 'COUNTERPRESS_COSMOS_CLIENT_ID', value: identity.properties.clientId }
          { name: 'COUNTERPRESS_STREAM_CLIENT_ID', value: identity.properties.clientId }
          { name: 'COUNTERPRESS_FEED_CLIENT_ID', value: identity.properties.clientId }
          { name: 'COUNTERPRESS_FEED_AUTH', value: 'managed-identity' }
          { name: 'COUNTERPRESS_EVENTHUB_NAMESPACE', value: '${events.name}.servicebus.windows.net' }
          { name: 'COUNTERPRESS_EVENTHUB_NAME', value: 'deliveries-phase4' }
          { name: 'COUNTERPRESS_CHECKPOINT_ENDPOINT', value: storage.properties.primaryEndpoints.blob }
          { name: 'COUNTERPRESS_CHECKPOINT_CONTAINER', value: 'eventhub-checkpoints-phase4' }
          { name: 'COUNTERPRESS_QUARANTINE_CONTAINER', value: 'rejected-deliveries-phase4' }
          { name: 'COUNTERPRESS_PUBSUB_ENDPOINT', value: 'https://${pubsub.properties.hostName}' }
          { name: 'COUNTERPRESS_PUBSUB_HUB', value: 'counterpress_phase4' }
          { name: 'COUNTERPRESS_ASSISTANT_MODEL', value: 'off' }
          { name: 'COUNTERPRESS_EDITORIAL', value: 'off' }
          { name: 'COUNTERPRESS_STUDIO', value: 'off' }
          { name: 'COUNTERPRESS_AGENT_TRACING', value: 'off' }
          { name: 'COUNTERPRESS_TELEMETRY', value: 'off' }
        ]
        probes: [
          { type: 'Startup', httpGet: { path: '/ready', port: 8000, scheme: 'HTTP' }, periodSeconds: 5, timeoutSeconds: 5, failureThreshold: 30 }
          { type: 'Readiness', httpGet: { path: '/ready', port: 8000, scheme: 'HTTP' }, periodSeconds: 10, timeoutSeconds: 5, failureThreshold: 3 }
          { type: 'Liveness', httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }, periodSeconds: 30, timeoutSeconds: 5, failureThreshold: 3 }
        ]
      }]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
          { name: 'eventhub-phase4', custom: {
            type: 'azure-eventhub'
            identity: identity.id
            metadata: {
              eventHubNamespace: events.name
              eventHubName: 'deliveries-phase4'
              consumerGroup: '$Default'
              storageAccountName: storage.name
              blobContainer: 'eventhub-checkpoints-phase4'
              checkpointStrategy: 'blobMetadata'
              unprocessedEventThreshold: '1'
              activationUnprocessedEventThreshold: '0'
            }
          } }
        ]
      }
    }
  }
  dependsOn: [journalRole, receiver, sender, blobRoles, publisher]
}
// Explicit scope IDs avoid Bicep loop-resource .id expansion leaking copyIndex()
// into outputs, where ARM cannot evaluate a resource copy-loop index.
var checkpointId = resourceId('Microsoft.Storage/storageAccounts/blobServices/containers', storage.name, 'default', 'eventhub-checkpoints-phase4')
var quarantineId = resourceId('Microsoft.Storage/storageAccounts/blobServices/containers', storage.name, 'default', 'rejected-deliveries-phase4')
// IDs are consumed privately by the guarded CLI; never print deployment output.
output cleanupIds array = [
  app.id
  journalRole.id
  receiver.id
  sender.id
  extensionResourceId(checkpointId, 'Microsoft.Authorization/roleAssignments', guid(checkpointId, identity.id, 'phase4-blob'))
  extensionResourceId(quarantineId, 'Microsoft.Authorization/roleAssignments', guid(quarantineId, identity.id, 'phase4-blob'))
  publisher.id
  feed.id
  checkpointId
  quarantineId
  journal.id
  identity.id
]
