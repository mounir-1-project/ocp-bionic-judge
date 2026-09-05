"""Script pour nettoyer le frontend JavaScript."""
import re

with open('api/static/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove GATE_LABEL constant
content = re.sub(r'const GATE_LABEL = \{[^}]+\};\n\n', '', content)

# Remove renderValidation function
content = re.sub(r'function renderValidation\(report\) \{.*?\}\n\n', '', content, flags=re.DOTALL)

# Remove renderBench function
content = re.sub(r'function renderBench\(result\) \{.*?\}\n\n', '', content, flags=re.DOTALL)

# Remove renderSensitivity function
content = re.sub(r'function renderSensitivity\(payload\) \{.*?\}\n\n', '', content, flags=re.DOTALL)

# Remove renderBenchFouling function
content = re.sub(r'function renderBenchFouling\(payload\) \{.*?\}\n\n', '', content, flags=re.DOTALL)

# Simplify renderMail function
old_mail_pattern = r'function renderMail\(status\) \{.*?for \(const id of \["mailTest", "mailGod"\]\).*?\}'
new_mail = '''function renderMail(status) {
  const chip = $('mailChip');
  if (!status) { chip.textContent = '—'; chip.dataset.tone = 'fault'; return; }
  const enabled = status.enabled ?? status.configured ?? false;
  chip.textContent = enabled ? 'Actif' : 'Inactif';
  chip.dataset.tone = enabled ? 'ok' : 'fault';
  const box = $('mailBox');
  if (!enabled) { box.innerHTML = '<p class="void">SMTP non configuré</p>'; return; }
  box.innerHTML = '<p>Envois: ' + (status.sent_count ?? 0) + ' | Destinataires: ' + (status.recipient_count ?? 0) + '</p>';
}'''
content = re.sub(r'function renderMail\(status\) \{.*?\n\}', new_mail, content, flags=re.DOTALL)

# Remove startup API calls
content = re.sub(r'  api\("/api/model/validation"\)\.then\(renderValidation\)\.catch\(\(\) => \{\}\);\n', '', content)
content = re.sub(r'  api\("/api/judge/evaluation"\)\.then\(renderBench\)\.catch\(\(\) => \{ \$\("benchScore"\)\.textContent = "—"; \}\);\n', '', content)
content = re.sub(r'  api\("/api/sensitivity"\)\.then\(renderSensitivity\)\.catch\(\(\) => \{[^}]+\}\);\n', '', content)
content = re.sub(r'  api\("/api/detection/fouling-bench\?severities=0\.05,0\.10,0\.20,0\.30&duration_days=60"\)\s*\.then\(renderBenchFouling\)\s*\.catch\(\(\) => \{[^}]+\}\);\n', '', content)

# Remove click handlers for runBench, runFouling, mailTest, mailGov
content = re.sub(r'  \$\("runBench"\)\.addEventListener\("click", async \(e\) => \{.*?\}\);\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'  \$\("runFouling"\)\.addEventListener\("click", async \(e\) => \{.*?\}\);\n\n', '', content, flags=re.DOTALL)

# Remove sendMail helper and mailTest/mailGov listeners
content = re.sub(r'  const sendMail = \(path, label\) => async \(e\) => \{.*?\n  \$\("mailGov"\)\.addEventListener\("click",[^)]+\);\n\n', '', content, flags=re.DOTALL)

with open('api/static/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('JavaScript cleanup complete!')
