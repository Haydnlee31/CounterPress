targetScope = 'resourceGroup'

param location string = resourceGroup().location
@minLength(3)
@maxLength(20)
param namePrefix string = 'counterpress'

@description('SHA-256 digest of the linux/amd64 image uploaded as counterpress. No tag or registry hostname.')
@minLength(71)
@maxLength(71)
param imageDigest string

@description('Enable only after deploying infra/cosmos.bicep and testing persistence.')
param useCosmos bool = false

@description('Enable only with Cosmos after deploying infra/streaming.bicep.')
param useStreaming bool = false

@description('Emit bounded numeric streaming telemetry; provision monitoring.bicep and telemetry-ingestion.bicep first.')
param useTelemetry bool = false

@description('Enable factual Studio only after browser/identity and Cosmos verification. Paid editorial remains off.')
param useStudio bool = false

@secure()
@description('Private runtime metadata with tenant_id, api_client_id and client_id; no keys or model endpoints.')
param studioIdentity object = {}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: 'cp${uniqueString(resourceGroup().id)}'
}
resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = {
  name: '${namePrefix}-env'
}
resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${namePrefix}-pull'
}

resource historyIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = if (useCosmos) {
  name: '${namePrefix}-history'
}
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = if (useCosmos) {
  name: 'cp-${uniqueString(resourceGroup().id)}'
}

resource streamIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = if (useStreaming) {
  name: '${namePrefix}-stream'
}
resource feedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = if (useStreaming) {
  name: '${namePrefix}-feed'
}
resource events 'Microsoft.EventHub/namespaces@2024-01-01' existing = if (useStreaming) {
  name: 'cp-events-${uniqueString(resourceGroup().id)}'
}
resource streamStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (useStreaming) {
  name: 'cpstream${uniqueString(resourceGroup().id)}'
}
resource pubsub 'Microsoft.SignalRService/webPubSub@2024-03-01' existing = if (useStreaming) {
  name: 'cp-live-${uniqueString(resourceGroup().id)}'
}

resource monitorRule 'Microsoft.Insights/dataCollectionRules@2023-03-11' existing = if (useTelemetry) { name: '${namePrefix}-ops-ingest' }

resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: namePrefix
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: union({ '${pullIdentity.id}': {} }, useCosmos ? { '${historyIdentity.id}': {} } : {}, useStreaming ? { '${streamIdentity.id}': {}, '${feedIdentity.id}': {} } : {})
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 1
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        { server: registry.properties.loginServer, identity: pullIdentity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'counterpress'
          image: '${registry.properties.loginServer}/counterpress@${imageDigest}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(useCosmos ? [
            { name: 'COUNTERPRESS_STORAGE', value: 'cosmos' }
            { name: 'COUNTERPRESS_COSMOS_ENDPOINT', value: cosmos!.properties.documentEndpoint }
            { name: 'COUNTERPRESS_COSMOS_DATABASE', value: 'counterpress' }
            { name: 'COUNTERPRESS_COSMOS_CONTAINER', value: 'histories' }
            { name: 'COUNTERPRESS_COSMOS_CLIENT_ID', value: historyIdentity!.properties.clientId }
          ] : [], useStreaming ? [
            { name: 'COUNTERPRESS_STREAMING', value: 'azure' }
            { name: 'COUNTERPRESS_TELEMETRY', value: useTelemetry ? 'on' : 'off' }
            { name: 'COUNTERPRESS_STREAM_CLIENT_ID', value: streamIdentity!.properties.clientId }
            { name: 'COUNTERPRESS_FEED_CLIENT_ID', value: feedIdentity!.properties.clientId }
            { name: 'COUNTERPRESS_FEED_AUTH', value: 'managed-identity' }
            { name: 'COUNTERPRESS_EVENTHUB_NAMESPACE', value: '${events!.name}.servicebus.windows.net' }
            { name: 'COUNTERPRESS_EVENTHUB_NAME', value: 'deliveries' }
            { name: 'COUNTERPRESS_CHECKPOINT_ENDPOINT', value: streamStorage!.properties.primaryEndpoints.blob }
            { name: 'COUNTERPRESS_PUBSUB_ENDPOINT', value: 'https://${pubsub!.properties.hostName}' }
          ] : [], useTelemetry ? [
            { name: 'COUNTERPRESS_MONITOR_ENDPOINT', value: monitorRule!.properties.endpoints.logsIngestion }
            { name: 'COUNTERPRESS_MONITOR_DCR_ID', value: monitorRule!.properties.immutableId }
          ] : [], useStudio ? [
            { name: 'COUNTERPRESS_STUDIO', value: 'entra' }
            { name: 'COUNTERPRESS_STUDIO_CLIENT_ID', value: studioIdentity.client_id }
            { name: 'COUNTERPRESS_ENTRA_TENANT_ID', value: studioIdentity.tenant_id }
            { name: 'COUNTERPRESS_ENTRA_AUDIENCE', value: studioIdentity.api_client_id }
            { name: 'COUNTERPRESS_EDITORIAL', value: 'off' }
          ] : [])
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/ready', port: 8000, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 5
              failureThreshold: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/ready', port: 8000, scheme: 'HTTP' }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      // Keep one replica for the bounded demo workload even with shared persistence.
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: concat([
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
        ], useStreaming ? [
          {
            name: 'eventhub'
            custom: {
              type: 'azure-eventhub'
              identity: streamIdentity!.id
              metadata: {
                eventHubNamespace: events!.name
                eventHubName: 'deliveries'
                consumerGroup: '$Default'
                storageAccountName: streamStorage!.name
                blobContainer: 'eventhub-checkpoints'
                checkpointStrategy: 'blobMetadata'
                unprocessedEventThreshold: '1'
                activationUnprocessedEventThreshold: '0'
              }
            }
          }
        ] : [])
      }
    }
  }
}

output appName string = app.name
