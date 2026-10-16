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

resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: namePrefix
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: union({ '${pullIdentity.id}': {} }, useCosmos ? { '${historyIdentity.id}': {} } : {})
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
          env: useCosmos ? [
            { name: 'COUNTERPRESS_STORAGE', value: 'cosmos' }
            { name: 'COUNTERPRESS_COSMOS_ENDPOINT', value: cosmos!.properties.documentEndpoint }
            { name: 'COUNTERPRESS_COSMOS_DATABASE', value: 'counterpress' }
            { name: 'COUNTERPRESS_COSMOS_CONTAINER', value: 'histories' }
            { name: 'COUNTERPRESS_COSMOS_CLIENT_ID', value: historyIdentity!.properties.clientId }
          ] : []
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
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
        ]
      }
    }
  }
}

output appName string = app.name
