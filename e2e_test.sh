python smithy-to-openapi/process_models.py --clean
npm run start-server -- --provider aws --registry $PROVIDER_REGISTRY_ROOT_DIR
npm run test-meta-routes -- aws --verbose
npm run stop-server