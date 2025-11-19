apiVersion: v1
kind: Secret
metadata:
  name: {{ include "cml.name" . }}-secret
  labels:
{{ include "cml.labels" . | indent 4 }}
type: Opaque
stringData:
{{- range $key, $value := .Values.secretEnv }}
  {{ $key }}: {{ $value | quote }}
{{- end }}
{{- if .Values.mongodb.enabled }}
  MONGO_ROOT_PASSWORD: {{ .Values.mongodb.auth.password | quote }}
{{- end }}
