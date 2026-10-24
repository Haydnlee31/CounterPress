targetScope = 'resourceGroup'
param location string = resourceGroup().location
param namePrefix string = 'counterpress'
param githubRepository string = 'Haydnlee31/CounterPress'
param githubEnvironment string = 'azure-demo'
@description('Immutable public GitHub owner ID; obtain from the repository API.')
param githubOwnerId string
@description('Immutable public GitHub repository ID; obtain from the repository API.')
param githubRepositoryId string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-deploy'
  location: location
}
resource federation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-environment'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${split(githubRepository, '/')[0]}@${githubOwnerId}/${split(githubRepository, '/')[1]}@${githubRepositoryId}:environment:${githubEnvironment}'
    audiences: ['api://AzureADTokenExchange']
  }
}
resource app 'Microsoft.App/containerApps@2025-07-01' existing = { name: namePrefix }
resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = { name: '${namePrefix}-env' }
resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = { name: 'cp${uniqueString(resourceGroup().id)}' }
resource role 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, namePrefix, 'image-deployer')
  properties: {
    roleName: '${namePrefix}-image-deployer-${uniqueString(resourceGroup().id)}'
    description: 'Update the existing CounterPress app, inspect revisions and deactivate staging revisions; no role assignments or data-plane access.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [{
      // Traffic weights and labels use the existing app write permission.
      // Revision reads verify readiness; deactivation cleans up staging only.
      // https://learn.microsoft.com/azure/role-based-access-control/permissions/compute#microsoftapp
      actions: [
        'Microsoft.App/containerApps/read'
        'Microsoft.App/containerApps/write'
        'Microsoft.App/containerApps/revisions/read'
        'Microsoft.App/containerApps/revisions/deactivate/action'
      ]
      notActions: []
      dataActions: []
      notDataActions: []
    }]
  }
}
resource appRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, identity.id, 'image-deployer')
  scope: app
  properties: { principalId: identity.properties.principalId, principalType: 'ServicePrincipal', roleDefinitionId: role.id }
}
resource registryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'AcrPush')
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec')
  }
}
// CLI reads registry metadata and the existing environment. No Contributor role.
resource registryReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'Reader')
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}
resource environmentReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(environment.id, identity.id, 'Reader')
  scope: environment
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}
