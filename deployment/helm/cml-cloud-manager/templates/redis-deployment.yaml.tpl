{{- if .Values.redis.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "cml.name" . }}-redis
  labels:
{{ include "cml.labels" . | indent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
      release: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app: redis
        release: {{ .Release.Name }}
    spec:
      containers:
        - name: redis
          image: {{ .Values.redis.image }}
          ports:
            - containerPort: {{ .Values.redis.port }}
          resources:
{{ toYaml .Values.redis.resources | indent 12 }}
          args: ["--save", "", "--appendonly", "no"]
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "cml.name" . }}-redis
  labels:
{{ include "cml.labels" . | indent 4 }}
spec:
  selector:
    app: redis
    release: {{ .Release.Name }}
  ports:
    - name: redis
      port: {{ .Values.redis.port }}
      targetPort: {{ .Values.redis.port }}
{{- end }}
