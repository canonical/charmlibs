# `spoe-auth/v0`

## Usage

This relation interface describes the expected behavior of any charm that can work with the haproxy charm to provide authentication capabilities through SPOE ( Stream Process Offloading Engine ).

## Direction

SPOE allows haproxy to be extended with middlewares. SPOA are agents that talk to haproxy using the Stream Process Offloading Protocol ( SPOP ).

Providers are agent charms that validates incoming requests, communicates to Haproxy the full redirect URL to the IDP in case of unauthenticated requests, receives the OIDC callback and finally issues a redirect to the original destination to set the authentication cookie on the client browser if the request is authenticated.

The haproxy-operator charm is the only requirer charm as of now.

## Behavior
### Provider

- Is expected to expose a TCP port receiving SPOE messages ( through SPOP ). This port needs to be communicated to the requirer ( haproxy ).
- Is expected to reply to the SPOE messages with the appropriate set-var Actions, mainly idicating whether the request is authenticated
and if not, what's the IDP redirect URL that haproxy need to use as the response.
- Is expected to expose an HTTP port receiving the OIDC callback requests. The hostname and path prefix used to route requests to
this port needs to be communicated to the requirer ( haproxy )

### Requirer ( haproxy )

- Is expected to use the information available in the relation data to perform the corresponding actions. Specifically:
  - Update the haproxy configuration to define SPOE message parameters, define the SPOP/redirect/callback backends and add routing rules accordingly


## Relation Data

### Provider

The provider exposes via its application databag informations about the SPOP and the OIDC callback endpoints via the `spop_port`, and `oidc_callback_*` attributes respectively. The provider also communicates the name of the variables for important flags such as "Is the user authenticated" (`var_authenticated`) or "The full URL to issue a redirect to the IDP" (`var_redirect_url`). The provider also exposes the name of the SPOE message, the event that should trigger the SPOE message and the name of the cookie to include in the SPOE message via the `message_name`, `event` and `cookie_name` attribute respectively.


#### Example
```yaml
unit_data:
  unit/0:
    address: 10.0.0.1

application_data:            
  spop_port: 12345
  event: on-frontend-http-request
  message_name: try-auth-oidc
  var_authenticated: sess.auth.is_authenticated
  var_redirect_url: sess.auth.redirect_url
  cookie_name: sessioncookie
  oidc_callback_port: 5000
  oidc_callback_path: /oauth2/callback
  hostname: auth.haproxy.internal
```

### Requirer
No data is communicated from the requirer side.