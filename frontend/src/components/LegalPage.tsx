import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import PublicNav from './PublicNav';
import { useT } from '../i18n';
import type { Language } from '../i18n';
import { legalContentByKey } from '../legalContent';

interface LegalPageProps {
  contentKey: 'kvkk' | 'terms' | 'privacy';
}

export default function LegalPage({ contentKey }: LegalPageProps) {
  const [lang, setLang] = useState<Language>('tr');
  const t = useT(lang);
  const doc = legalContentByKey[contentKey][lang];

  return (
    <div className="min-h-screen bg-[#F9F7F2] font-sans text-[#4A443F]">
      <PublicNav lang={lang} onLangChange={setLang} />

      <div className="max-w-3xl mx-auto px-6 py-16">
        {/* Göz ardı edilemeyecek uyarı bandı — bilerek her üç sayfada da bileşene gömülü */}
        <div className="flex items-start gap-3 bg-amber-50 border border-amber-300 text-amber-900 rounded-xl px-5 py-4 mb-10">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-xs font-medium leading-relaxed">{t.legalDisclaimer}</p>
        </div>

        <h1 className="text-2xl font-black text-[#4A443F] mb-2">{doc.title}</h1>
        <p className="text-[10px] text-[#9E958C] font-semibold uppercase tracking-wider mb-10">
          {t.legalLastUpdated}: {doc.lastUpdated}
        </p>

        <div className="space-y-8">
          {doc.sections.map((section) => (
            <div key={section.heading}>
              <h2 className="text-sm font-bold text-[#4A443F] mb-2">{section.heading}</h2>
              {section.body.map((p, i) => (
                <p key={i} className="text-xs text-[#6B645E] leading-relaxed mb-2">{p}</p>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
