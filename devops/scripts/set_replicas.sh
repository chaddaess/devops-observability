#!/usr/bin/env bash
# Usage: ./scripts/set_replicas.sh <nb_replicas>


REPLICAS="${1:-1}"


cat > src/main/resources/myapp-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
 name: myapp
spec:
 replicas: ${REPLICAS}
 selector:
   matchLabels:
     app: myapp
 template:
   metadata:
     labels:
       app: myapp
   spec:
     containers:
       - name: myapp
         image: myapp:secure
         ports:
           - containerPort: 8080
         envFrom:
           - secretRef:
               name: myapp-secrets
EOF


echo "✔ myapp-deployment.yaml mis à jour avec replicas = ${REPLICAS}"

