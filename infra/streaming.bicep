targetScope = 'resourceGroup'
param location string = resourceGroup().location
param namePrefix string = 'counterpress'

resource streamIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-stream'
  location: location
}
resource feedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-feed'
  location: location
}
resource events 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'cp-events-${uniqueString(resourceGroup().id)}'
  location: location
  sku: { name: 'Basic', tier: 'Basic', capacity: 1 }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    isAutoInflateEnabled: false
  }
}
resource feed 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: events
  name: 'deliveries'
  properties: { partitionCount: 1, messageRetentionInDays: 1 }
}
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'cpstream${uniqueString(resourceGroup().id)}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Enabled'
    accessTier: 'Hot'
  }
}
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for container in ['eventhub-checkpoints', 'rejected-deliveries']: {
  parent: blobs
  name: container
  properties: { publicAccess: 'None' }
}]
resource pubsub 'Microsoft.SignalRService/webPubSub@2024-03-01' = {
  name: 'cp-live-${uniqueString(resourceGroup().id)}'
  location: location
  sku: { name: 'Free_F1', tier: 'Free', capacity: 1 }
  properties: { disableLocalAuth: true, publicNetworkAccess: 'Enabled', disableAadAuth: false }
}
resource receiverRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feed.id, streamIdentity.id, 'receiver')
  scope: feed
  properties: {
    principalId: streamIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde')
  }
}
resource senderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feed.id, feedIdentity.id, 'sender')
  scope: feed
  properties: {
    principalId: feedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2b629674-e913-4c01-ae53-ef4638d8f975')
  }
}
resource blobRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (container, i) in ['eventhub-checkpoints', 'rejected-deliveries']: {
  name: guid(containers[i].id, streamIdentity.id, 'blob-writer')
  scope: containers[i]
  properties: {
    principalId: streamIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}]
resource pubsubRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(pubsub.id, streamIdentity.id, 'pubsub-service')
  scope: pubsub
  properties: {
    principalId: streamIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '12cf5a90-567b-43ae-8102-96cf46c7d9b4')
  }
}
