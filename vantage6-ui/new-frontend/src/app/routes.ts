export const routePaths = {
  login: '/login',
  start: '/start',
  home: '/',
  adminHome: '/admin',
  organizations: '/admin/organizations',
  organizationCreate: '/admin/organizations/create',
  organizationEdit: '/admin/organizations/edit',
  organization: '/admin/organizations',
  collaborations: '/admin/collaborations',
  collaborationCreate: '/admin/collaborations/create',
  collaborationEdit: '/admin/collaborations/edit',
  collaboration: '/admin/collaborations',
  users: '/admin/users',
  userCreate: '/admin/users/create',
  user: '/admin/users',
  nodes: '/admin/nodes',
  tasks: '/tasks',
  taskCreate: '/tasks/create',
  task: '/tasks'
};

export const routerConfig = {
  login: 'login',
  start: 'start',
  home: '',
  admin: 'admin',
  adminHome: '',
  organizations: 'organizations',
  organizationCreate: 'organizations/create',
  organizationEdit: 'organizations/edit/:id',
  organization: 'organizations/:id',
  collaborations: 'collaborations',
  collaborationCreate: 'collaborations/create',
  collaborationEdit: 'collaborations/edit/:id',
  collaboration: 'collaborations/:id',
  users: 'users',
  userCreate: 'users/create',
  user: 'users/:id',
  nodes: 'nodes',
  tasks: 'tasks',
  taskCreate: 'tasks/create',
  task: 'tasks/:id'
};
