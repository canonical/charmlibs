.. meta::
   :description: Understand OAuth 2.0 and OpenID Connect (OIDC) concepts, public vs. confidential clients, and various authentication flows.

.. _oauth2-oidc-explained:

Understanding OAuth 2.0 and OpenID Connect (OIDC)
=================================================

OAuth 2.0 Overview
------------------

OAuth 2.0 is an authorization framework that enables applications to obtain limited access to user accounts on an HTTP service. It works by delegating user authentication to an authorization server, allowing applications to access user resources without exposing user credentials.

OAuth 2.0 defines different grant types to accommodate various authentication scenarios, including:

* **Authorization Code Grant** (Recommended for web applications)
* **Client Credentials Grant** (For machine-to-machine authentication)
* **Device Flow Grant** (For devices with limited input capabilities)
* **Implicit Grant** (Deprecated due to security concerns)
* **Password Credentials Grant** (Limited to trusted applications)

Access and Refresh Tokens
^^^^^^^^^^^^^^^^^^^^^^^^^

* **Access Tokens**: Short-lived tokens used to access protected resources on behalf of the user. These tokens are included in API requests to prove authorization.
* **Refresh Tokens**: Long-lived tokens that can be used to obtain new access tokens without requiring the user to log in again. These are typically used in long-lived sessions.

Client ID, Client Secret, and Redirect URI
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OAuth 2.0 relies on a **Client ID** and, for confidential clients, a **Client Secret** to authenticate applications. The Client ID is a public identifier, while the Client Secret should be kept secure and is used to authenticate confidential clients when exchanging authorization codes or obtaining access tokens.

The **Redirect URI** is a registered URL where the authorization server sends the user after authentication. This URL must match the registered redirect URI for the client application to prevent unauthorized redirections and attacks such as authorization code interception.

Proof Key for Code Exchange (PKCE)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

PKCE (Proof Key for Code Exchange) is an extension to the Authorization Code Flow designed to improve security, especially for public clients such as single-page applications and mobile apps. It mitigates authorization code interception attacks by requiring a dynamically generated code challenge and verifier.

Public vs. Confidential Clients
-------------------------------

OAuth 2.0 distinguishes between two types of clients based on their ability to keep credentials secure:

* **Confidential Clients**: Applications that can securely store credentials, such as backend servers. These clients use a Client ID and Client Secret for authentication.
* **Public Clients**: Applications that cannot securely store credentials, such as mobile apps and single-page applications (SPAs). These clients typically use PKCE to enhance security in the Authorization Code Flow instead of relying on a Client Secret.

OpenID Connect (OIDC) Overview
------------------------------

What is OpenID Connect (OIDC)?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OpenID Connect (OIDC) is an identity layer built on top of the OAuth 2.0 protocol. It allows clients to verify the identity of an end-user based on authentication performed by an authorization server, as well as obtain basic profile information about the user.

OIDC is widely used for Single Sign-On (SSO) and identity federation, enabling secure authentication across multiple applications and services.

How Does OIDC Work?
-------------------

OIDC extends OAuth 2.0 by introducing an **ID Token**, which contains user authentication data in a JSON Web Token (JWT) format. The authentication flow typically involves the following steps:

1. **User Authentication Request**: The client application redirects the user to the OpenID Provider (OP) for authentication.
2. **User Authenticates**: The user provides their credentials (e.g., username and password) to the OP.
3. **Authorization Grant**: If authentication is successful, the OP issues an authorization code.
4. **Token Exchange**: The client application exchanges the authorization code for an ID Token and an Access Token.
5. **User Information Retrieval**: The client can retrieve additional user information from the UserInfo endpoint using the Access Token.

Key Components of OIDC
----------------------

* **OpenID Provider (OP)**: The authorization server that authenticates the user and issues tokens.
* **Relying Party (RP)**: The application that relies on the OP for user authentication.
* **ID Token**: A JWT that contains claims about the authenticated user.
* **Access Token**: A token that grants access to protected resources on behalf of the user.
* **Refresh Token**: A long-lived token used to obtain new access tokens without requiring user interaction.
* **UserInfo Endpoint**: An API endpoint that provides additional user details.
* **Scopes and Claims**: Define the level of access and user data available to the client application.

Scopes in OAuth 2.0 and OIDC
----------------------------

**Scopes** define the level of access that a client application is requesting from the authorization server. They allow fine-grained control over which resources a client can access. Some common scopes include:

* ``openid``: Required for OIDC; indicates the request for an ID Token.
* ``profile``: Grants access to basic user profile information such as name and email.
* ``email``: Grants access to the user’s email address.
* ``offline_access``: Grants the ability to obtain a refresh token for long-term access.
* ``custom_scopes``: Applications can define their own custom scopes to control access to specific APIs.

When a client requests a scope, the authorization server may issue access tokens with only the granted scopes based on user consent and security policies.

JSON Web Tokens (JWTs)
^^^^^^^^^^^^^^^^^^^^^^

OIDC relies on **JSON Web Tokens (JWTs)** for secure and structured token exchange. JWTs are compact, URL-safe tokens containing claims about a user or an authorization request. They are signed and optionally encrypted, ensuring integrity and security.

OIDC Authentication Flows
-------------------------

Authorization Code Flow (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The most secure flow, typically used for web applications. The authorization code is exchanged for tokens using a secure backend channel, often with PKCE for added security.

Client Credentials Flow
^^^^^^^^^^^^^^^^^^^^^^^

Used for machine-to-machine authentication without user involvement. In this flow, the client application authenticates itself using its client ID and secret to obtain an access token, which it can then use to access protected resources.

Device Flow Grant
^^^^^^^^^^^^^^^^^

Designed for devices with limited input capabilities, such as smart TVs, IoT devices and headless VMs. The user enters a code on a separate device to authenticate and authorize access.

Implicit Flow (Deprecated)
^^^^^^^^^^^^^^^^^^^^^^^^^^

Previously used for SPAs but now discouraged due to security concerns. Tokens were issued directly in the browser without a backend exchange.

Hybrid Flow
^^^^^^^^^^^

A combination of Authorization Code and Implicit Flow, providing both an authorization code and an ID Token.

Why Use OIDC?
-------------

* **Standardized Authentication**: Provides a well-defined authentication mechanism.
* **Interoperability**: Works across different platforms and providers.
* **Security**: Uses cryptographic mechanisms to ensure token integrity.
* **Seamless User Experience**: Enables SSO across multiple applications.

Implementing OIDC with Canonical Identity Platform
--------------------------------------------------

The `Canonical Identity Platform <https://charmhub.io/topics/canonical-identity-platform>`_ provides a robust OIDC implementation, enabling secure authentication and authorization for your applications. With support for modern identity standards, it ensures seamless user authentication across cloud-native and enterprise environments.

To get started, refer to the official documentation and integration guides available.
