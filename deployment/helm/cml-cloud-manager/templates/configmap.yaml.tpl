apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "cml.name" . }}-config
  labels:
{{ include "cml.labels" . | indent 4 }}
data:
{{- range $key, $value := .Values.env }}
  {{ $key }}: {{ $value | quote }}
{{- end }}
