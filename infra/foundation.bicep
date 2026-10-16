targetScope = 'resourceGroup'

@description('Azure region chosen for the dedicated demo resource group.')
param location string = resourceGroup().location

@minLength(3)
@maxLength(20)
@description('Lowercase letters, digits and hyphens; start with a letter.')
param namePrefix string = 'counterpress'

var registryName = 'cp${uniqueString(resourceGroup().id)}'

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    roleAssignmentMode: 'LegacyRegistryPermissions'
    publicNetworkAccess: 'Enabled'
    policies: {
      azureADAuthenticationAsArmPolicy: { status: 'enabled' }
    }
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-pull'
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullIdentity.id, 'AcrPull')
  scope: registry
  properties: {
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: {
    // Log streaming only for the smoke stage; no paid Log Analytics workspace yet.
    appLogsConfiguration: { destination: 'none' }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}

output registryName string = registry.name
output environmentName string = environment.name
output pullIdentityName string = pullIdentity.name
