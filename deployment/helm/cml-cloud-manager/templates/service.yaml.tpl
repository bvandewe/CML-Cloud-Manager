apiVersion: v1
kind: Service
metadata:
  name: {{ include "cml.name" . }}
  labels:
{{ include "cml.labels" . | indent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
{{ include "cml.selectorLabels" . | indent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
