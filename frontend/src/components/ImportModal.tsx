import { useRef, useState, DragEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Upload, X, FileSpreadsheet, AlertCircle, CheckCircle2 } from 'lucide-react';
import { UserSettings } from '../types';
import { useT, Translations } from '../i18n';
import { api } from '../services/api';

interface ImportModalProps {
  settings: UserSettings;
  onClose: () => void;
  onComplete: () => void;
}

type Step = 'upload' | 'mapping' | 'result';

// Backend ile birebir aynı taksonomi (bkz. backend/imports_engine.py VALID_ASSET_CLASSES
// ve DashboardView'daki manuel ekleme akışı) — burada yeni bir sınıf UYDURULMADI.
const ASSET_CLASS_OPTIONS: { value: string; labelKey: keyof Translations }[] = [
  { value: 'ABD Hisse/ETF', labelKey: 'importAssetClassStock' },
  { value: 'BIST Hissesi', labelKey: 'importAssetClassBist' },
  { value: 'Kripto', labelKey: 'importAssetClassCrypto' },
  { value: 'TEFAS Fonu', labelKey: 'importAssetClassFund' },
  { value: 'AMFI Fonu', labelKey: 'importAssetClassAmfi' },
  { value: 'FixedIncome', labelKey: 'importAssetClassFixedIncome' },
  { value: 'Nakit', labelKey: 'importAssetClassCash' },
];

const REQUIRED_FIELDS: { key: string; labelKey: keyof Translations }[] = [
  { key: 'ticker', labelKey: 'importFieldTicker' },
  { key: 'quantity', labelKey: 'importFieldQuantity' },
  { key: 'buy_price', labelKey: 'importFieldPrice' },
  { key: 'buy_date', labelKey: 'importFieldDate' },
];

const OPTIONAL_FIELDS: { key: string; labelKey: keyof Translations }[] = [
  { key: 'buy_currency', labelKey: 'importFieldCurrency' },
  { key: 'asset_class', labelKey: 'importFieldAssetClass' },
];

export default function ImportModal({ settings, onClose, onComplete }: ImportModalProps) {
  const t = useT(settings.language);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>('upload');
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [importId, setImportId] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [previewRows, setPreviewRows] = useState<Record<string, string | null>[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [assetClassDefault, setAssetClassDefault] = useState('');
  const [currencyDefault, setCurrencyDefault] = useState(settings.baseCurrency || 'TRY');

  const [result, setResult] = useState<{ created: number; skipped: number; errors: { row: number; reason: string }[] } | null>(null);

  const handleFile = async (file: File) => {
    setError(null);
    setLoading(true);
    try {
      const preview = await api.importPreview(file);
      setImportId(preview.import_id);
      setColumns(preview.columns);
      setRowCount(preview.row_count);
      setPreviewRows(preview.preview_rows);
      setWarnings(preview.warnings);
      setMapping(preview.suggested_mapping);
      setStep('mapping');
    } catch (err: any) {
      setError(err.message || 'İşlem başarısız.');
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const missingRequired = REQUIRED_FIELDS.filter(f => !mapping[f.key]);

  const handleConfirm = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await api.importConfirm({
        import_id: importId,
        mapping,
        asset_class_default: assetClassDefault || null,
        buy_currency_default: currencyDefault,
      });
      setResult(res);
      setStep('result');
      if (res.created > 0) onComplete();
    } catch (err: any) {
      setError(err.message || 'İşlem başarısız.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4">
        <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
          className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
          <div className="px-6 py-4 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F1EFE9]">
            <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
              <FileSpreadsheet className="w-4 h-4 text-[#8C9A86]" />{t.importModalTitle}
            </h3>
            <button onClick={onClose} aria-label={t.detailClose} className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors"><X className="w-4 h-4" /></button>
          </div>

          <div className="p-6 space-y-4 overflow-y-auto custom-scrollbar">
            {error && (
              <div className="flex items-start gap-2 bg-[#B5836F]/10 border border-[#B5836F]/30 rounded-lg px-3 py-2.5 text-[12px] text-[#B5836F] font-medium">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {step === 'upload' && (
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-xl px-6 py-14 cursor-pointer transition-colors ${dragOver ? 'border-[#8C9A86] bg-[#8C9A86]/5' : 'border-[#E8E2D9] hover:border-[#8C9A86]/50'}`}
              >
                <Upload className={`w-8 h-8 ${loading ? 'animate-pulse' : ''} text-[#8C9A86]`} />
                <p className="text-sm font-semibold text-[#2D2926] text-center">
                  {loading ? t.importParsing : t.importDropHint}
                </p>
                <p className="text-[11px] text-[#9E958C]">{t.importSupportedFormats}</p>
                <button type="button" disabled={loading}
                  className="mt-1 px-5 py-2 bg-[#8C9A86] hover:bg-[#7A8874] disabled:opacity-40 text-white text-[11px] font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">
                  {t.importChooseFile}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                    e.target.value = '';
                  }}
                />
              </div>
            )}

            {step === 'mapping' && (
              <div className="space-y-4">
                <p className="text-[11px] font-bold text-[#6B645E] uppercase tracking-wider">{t.importRowsFound(rowCount)}</p>

                {warnings.length > 0 && (
                  <div className="bg-[#C9A876]/10 border border-[#C9A876]/30 rounded-lg px-3 py-2.5 space-y-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C]">{t.importWarningsTitle}</p>
                    {warnings.map((w, i) => <p key={i} className="text-[12px] text-[#6B645E]">{w}</p>)}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {[...REQUIRED_FIELDS, ...OPTIONAL_FIELDS].map(f => (
                    <div key={f.key}>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">
                        {t[f.labelKey] as string}{REQUIRED_FIELDS.some(r => r.key === f.key) ? ' *' : ''}
                      </label>
                      <select
                        value={mapping[f.key] ?? ''}
                        onChange={(e) => setMapping(prev => ({ ...prev, [f.key]: e.target.value || null }))}
                        className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold"
                      >
                        <option value="">{t.importNotMapped}</option>
                        {columns.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#E8E2D9]">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.importDefaultAssetClass}</label>
                    <select
                      value={assetClassDefault}
                      onChange={(e) => setAssetClassDefault(e.target.value)}
                      className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold"
                    >
                      <option value="">{t.importSelectAssetClass}</option>
                      {ASSET_CLASS_OPTIONS.map(o => <option key={o.value} value={o.value}>{t[o.labelKey] as string}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.importDefaultCurrency}</label>
                    <select
                      value={currencyDefault}
                      onChange={(e) => setCurrencyDefault(e.target.value)}
                      className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold"
                    >
                      <option value="TRY">TRY</option>
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                      <option value="GBP">GBP</option>
                      <option value="INR">INR</option>
                    </select>
                  </div>
                </div>

                {previewRows.length > 0 && (
                  <div className="overflow-x-auto border border-[#E8E2D9] rounded-lg">
                    <table className="w-full text-[11px] font-mono">
                      <thead className="bg-[#F1EFE9]">
                        <tr>
                          {columns.map(c => <th key={c} className="px-2.5 py-1.5 text-left font-bold text-[#6B645E] whitespace-nowrap">{c}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {previewRows.slice(0, 5).map((row, i) => (
                          <tr key={i} className="border-t border-[#E8E2D9]">
                            {columns.map(c => <td key={c} className="px-2.5 py-1.5 text-[#2D2926] whitespace-nowrap">{row[c] ?? ''}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {step === 'result' && result && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-[#8C9A86]">
                  <CheckCircle2 className="w-5 h-5" />
                  <p className="text-sm font-bold text-[#2D2926]">{t.importResultTitle}</p>
                </div>
                <p className="text-sm text-[#2D2926] font-semibold">{t.importCreatedCount(result.created)}</p>
                {result.skipped > 0 && <p className="text-sm text-[#6B645E]">{t.importSkippedCount(result.skipped)}</p>}
                {result.errors.length > 0 && (
                  <div className="bg-[#F1EFE9] border border-[#E8E2D9] rounded-lg px-3 py-2.5 max-h-48 overflow-y-auto custom-scrollbar space-y-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C]">{t.importErrorsTitle}</p>
                    {result.errors.map((e, i) => (
                      <p key={i} className="text-[12px] text-[#6B645E]">
                        <span className="font-mono font-bold">#{e.row + 1}</span> — {e.reason}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="px-6 py-4 border-t border-[#E8E2D9] flex justify-end gap-3 bg-[#F9F7F2]">
            {step === 'mapping' && (
              <>
                <button type="button" onClick={() => setStep('upload')}
                  className="px-5 py-2 border border-[#E8E2D9] text-xs font-bold text-[#6B645E] rounded-full hover:bg-[#F1EFE9] transition-all">
                  {t.importBack}
                </button>
                <button type="button" onClick={handleConfirm} disabled={loading || missingRequired.length > 0}
                  className="px-6 py-2.5 bg-[#8C9A86] hover:bg-[#7A8874] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">
                  {t.importSubmit}
                </button>
              </>
            )}
            {step === 'result' && (
              <button type="button" onClick={onClose}
                className="px-6 py-2.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white text-xs font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">
                {t.importDone}
              </button>
            )}
            {step === 'upload' && (
              <button type="button" onClick={onClose}
                className="px-5 py-2 border border-[#E8E2D9] text-xs font-bold text-[#6B645E] rounded-full hover:bg-[#F1EFE9] transition-all">
                {t.importCancel}
              </button>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
