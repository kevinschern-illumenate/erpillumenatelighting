# Dealer Role Documentation

## Overview

The **Dealer** role is designed for external dealer/distributor users who need access to the ilLumenate Lighting portal and ERP features. Dealers can manage projects, configure fixtures, create orders, and invite external collaborators for their customers.

## Role Capabilities

### What Dealers Can Do

1. **Projects & Schedules**
   - Create projects for their company (Customer)
   - View all projects created by their company
   - Create fixture schedules within projects
   - Configure fixtures using the configurator
   - Request drawings/exports

2. **Sales Orders**
   - Create Sales Orders from fixture schedules
   - View their company's Sales Orders
   - Track order status and delivery

3. **Customers & Contacts**
   - Create new Customer records
   - Create new Contact records (auto-linked to their company)
   - View all customers and contacts associated with their company

4. **Collaborator Management**
   - Invite external collaborators to specific projects
   - Set collaborator access level (VIEW or EDIT)
   - Remove collaborators from projects

### What Dealers Cannot Do

- Delete projects or schedules (only System Managers can)
- Modify fixture templates or spec documents
- Access other companies' data
- Grant Dealer role to external collaborators

## External Collaborators

Dealers can invite external users to collaborate on specific projects. These collaborators:

- Only have access to the specific project(s) they are invited to
- Receive the "Website User" role (not "Dealer")
- Cannot see other projects, customers, or company data
- Cannot invite other collaborators

### Collaborator Access Levels

- **VIEW**: Can view the project and its schedules but cannot make changes
- **EDIT**: Can view and modify the project and its schedules

## Setting Up a Dealer User

1. Create a new User in ERPNext
2. Assign the "Dealer" role to the user
3. Create a Contact record for the user
4. Link the Contact to the appropriate Customer record

## API Endpoints

The following API endpoints are available for dealer functionality:

### `get_user_role_info`
Get current user's role information (is_dealer, is_internal, etc.)

### `invite_project_collaborator`
Invite an external collaborator to a project.

Parameters:
- `project_name`: The project ID
- `email`: Collaborator's email address
- `first_name`: Optional first name
- `last_name`: Optional last name
- `access_level`: "VIEW" or "EDIT"
- `send_invite`: 1 to send email, 0 to skip

### `remove_project_collaborator`
Remove a collaborator from a project.

Parameters:
- `project_name`: The project ID
- `user_email`: Collaborator's email address

### `get_company_contacts`
Get all contacts associated with the dealer's company.

### `create_contact`
Create a new contact (auto-linked to dealer's company).

### `get_company_customers`
Get all customers the dealer's company can access.

## Permission Model

```
┌─────────────────────────────────────────────────────────────┐
│                    System Manager                            │
│                 (Full access to all data)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Dealer                                 │
│        (Access to their company's projects & data)          │
│  - All projects where owner_customer = their customer       │
│  - All schedules for those projects                         │
│  - Can create customers, contacts, orders                   │
│  - Can invite external collaborators                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               External Collaborator                          │
│         (Access only to projects they're invited to)        │
│  - Cannot see other projects                                │
│  - Cannot create customers or invite others                 │
│  - VIEW or EDIT access per project                          │
└─────────────────────────────────────────────────────────────┘
```

## Installation

The Dealer role is automatically created when the ilLumenate Lighting app is installed. To manually create or update the role:

```python
from illumenate_lighting.illumenate_lighting.install import create_dealer_role, setup_dealer_permissions

# Create the role
create_dealer_role()

# Set up permissions on DocTypes
setup_dealer_permissions()
```
