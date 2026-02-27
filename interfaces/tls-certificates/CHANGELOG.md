# 1.8.1 - 27 February 2025

Cleanup secrets when relation is removed.

# 1.8.0 - 24 February 2025

Introduce the import_private_key public function to allow requirers to dynamically import an external public key.

# 1.7.0 - 18 February 2025

Introduce the APP_AND_UNIT mode so requirers can request both APP and UNIT certificates using one integration.

# 1.6.1 - 05 February 2025

Make `CertificateRequestAttributes` hashable to prevent unnecessary recreation of certificate requests in relation data.

# 1.6.0 - 27 January 2025

Add a safety net to ensure renewing expiring certificates.

# 1.5.0 - 27 January 2025

Add a public helper function to get the ID of the lib generated private key secret.

# 1.4.0 - 20 January 2025

Add a helper function in TLSCertificatesProvidesV4 to get the ProviderCertificateError objects from the relation data.

# 1.3.0 - 17 December 2025

Introduce the error field in relation data and specify error codes.

# 1.2.0 - 05 December 2025

Adding missing **hash**() functions.

# 1.1.0 - 27 November 2025

Importing changes from 4.26 version of the lib on Charmhub and releasing.

# 1.0.0.post2 - 19 November 2025

Correct docs URL in README.md.

# 1.0.0.post1 - 13 October 2025

Correct interface name in docs.

# 1.0.0.post0 - 7 October 2025

Fix docs link in readme.

# 1.0.0 - 2 October 2025

Migration of `tls_certificates_interface.tls_certificates` v4.22.
