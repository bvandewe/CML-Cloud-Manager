{{- if .Values.mongodb.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "cml.name" . }}-mongodb
  labels:
{{ include "cml.labels" . | indent 4 }}
spec:
  ports:
    - port: {{ .Values.mongodb.port }}
      name: mongo
  clusterIP: None
  selector:
    app: mongodb
    release: {{ .Release.Name }}
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "cml.name" . }}-mongodb
  labels:
{{ include "cml.labels" . | indent 4 }}
spec:
  serviceName: {{ include "cml.name" . }}-mongodb
  replicas: 1
  selector:
    matchLabels:
      app: mongodb
      release: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app: mongodb
        release: {{ .Release.Name }}
    spec:
      containers:
        - name: mongodb
          image: {{ .Values.mongodb.image }}
          ports:
            - containerPort: {{ .Values.mongodb.port }}
              name: mongo
          env:
            - name: MONGO_INITDB_ROOT_USERNAME
              value: {{ .Values.mongodb.auth.username | quote }}
            - name: MONGO_INITDB_ROOT_PASSWORD
              value: {{ .Values.mongodb.auth.password | quote }}
          resources:
{{ toYaml .Values.mongodb.resources | indent 12 }}
          volumeMounts:
            - name: mongo-data
              mountPath: /data/db
  volumeClaimTemplates:
    - metadata:
        name: mongo-data
        labels:
{{ include "cml.labels" . | indent 10 }}
      spec:
        accessModes: {{ toYaml .Values.mongodb.persistence.accessModes | nindent 10 }}
        resources:
          requests:
            storage: {{ .Values.mongodb.persistence.size }}
        {{- if .Values.mongodb.persistence.storageClass }}
        storageClassName: {{ .Values.mongodb.persistence.storageClass }}
        {{- end }}
{{- end }}
