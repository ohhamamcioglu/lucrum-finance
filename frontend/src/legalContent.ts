export interface LegalSection {
  heading: string;
  body: string[];
}

export interface LegalDocument {
  title: string;
  lastUpdated: string;
  sections: LegalSection[];
}

export interface LegalContentEntry {
  tr: LegalDocument;
  en: LegalDocument;
}

const LAST_UPDATED = '2026-07-01';

export const kvkkContent: LegalContentEntry = {
  tr: {
    title: 'Kişisel Verilerin Korunması Aydınlatma Metni (KVKK)',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Veri Sorumlusu',
        body: [
          '6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") uyarınca, LUCRUM Finance ("Veri Sorumlusu", "Şirket") olarak, hizmetlerimizi kullanırken elde ettiğimiz kişisel verilerinizin işlenmesine ilişkin sizi bilgilendirmek isteriz.',
        ],
      },
      {
        heading: '2. İşlenen Kişisel Veri Kategorileri',
        body: [
          'Kimlik bilgileri (ad soyad), iletişim bilgileri (e-posta adresi), hesap bilgileri (şifre hash\'i, oturum/refresh token bilgileri), portföy ve işlem verileri (varlık pozisyonları, alım-satım işlemleri, hedef dağılımlar, fiyat alarmları), abonelik ve faturalama tercihleri, kullanım/log verileri (giriş zamanları, IP adresi, hata izleme kayıtları).',
        ],
      },
      {
        heading: '3. İşleme Amaçları',
        body: [
          'Kullanıcı hesabının oluşturulması ve kimlik doğrulaması, portföy takibi ve analiz hizmetlerinin sunulması, abonelik planının yönetimi, hizmet kalitesinin iyileştirilmesi ve hata izleme, yasal yükümlülüklerin yerine getirilmesi, kullanıcı destek taleplerinin karşılanması.',
        ],
      },
      {
        heading: '4. Hukuki Sebep',
        body: [
          'Kişisel verileriniz, KVKK madde 5\'te belirtilen "bir sözleşmenin kurulması veya ifasıyla doğrudan doğruya ilgili olması", "veri sorumlusunun hukuki yükümlülüğünü yerine getirebilmesi için zorunlu olması" ve "ilgili kişinin temel hak ve özgürlüklerine zarar vermemek kaydıyla veri sorumlusunun meşru menfaatleri için veri işlenmesinin zorunlu olması" hukuki sebeplerine dayanılarak işlenmektedir.',
        ],
      },
      {
        heading: '5. Aktarım',
        body: [
          'Kişisel verileriniz, hizmetin sunulabilmesi için gerekli olan bulut altyapı sağlayıcıları, e-posta gönderim hizmeti sağlayıcısı ve hata izleme (Sentry) hizmeti gibi yurt içi/yurt dışı hizmet sağlayıcılarla, yalnızca hizmetin gerektirdiği ölçüde ve gerekli teknik/idari tedbirler alınarak paylaşılabilir. Şu an için üçüncü taraf bir ödeme sağlayıcısıyla veri paylaşımı yapılmamaktadır (ödeme altyapısı henüz canlıya alınmamıştır).',
        ],
      },
      {
        heading: '6. İlgili Kişi Hakları (KVKK Madde 11)',
        body: [
          'KVKK\'nın 11. maddesi uyarınca; kişisel verinizin işlenip işlenmediğini öğrenme, işlenmişse buna ilişkin bilgi talep etme, işlenme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenme, yurt içinde/yurt dışında aktarıldığı üçüncü kişileri bilme, eksik/yanlış işlenmişse düzeltilmesini isteme, silinmesini/yok edilmesini isteme, işlenen verilerin münhasıran otomatik sistemler ile analiz edilmesi sonucu aleyhinize bir sonucun ortaya çıkmasına itiraz etme ve kanuna aykırı işleme sebebiyle zarara uğramanız halinde zararın giderilmesini talep etme haklarına sahipsiniz.',
          'Bu haklarınızı kullanmak için hesap ayarlarınız üzerinden bizimle iletişime geçebilirsiniz.',
        ],
      },
    ],
  },
  en: {
    title: 'Personal Data Protection Notice (KVKK)',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Data Controller',
        body: [
          'Under Turkish Law No. 6698 on the Protection of Personal Data ("KVKK"), LUCRUM Finance ("Data Controller", "Company") informs you about how your personal data is processed while using our services.',
        ],
      },
      {
        heading: '2. Categories of Personal Data Processed',
        body: [
          'Identity information (full name), contact information (email address), account information (password hash, session/refresh token data), portfolio and transaction data (asset positions, buy/sell transactions, target allocations, price alerts), subscription and billing preferences, usage/log data (login times, IP address, error tracking records).',
        ],
      },
      {
        heading: '3. Purposes of Processing',
        body: [
          'Creating and authenticating user accounts, providing portfolio tracking and analytics services, managing subscription plans, improving service quality and error tracking, fulfilling legal obligations, responding to customer support requests.',
        ],
      },
      {
        heading: '4. Legal Basis',
        body: [
          'Your personal data is processed based on the legal grounds set out in Article 5 of KVKK, including "processing is directly related to the establishment or performance of a contract", "processing is mandatory for the data controller to fulfil its legal obligations", and "processing is mandatory for the legitimate interests of the data controller, provided that this does not harm the fundamental rights and freedoms of the data subject".',
        ],
      },
      {
        heading: '5. Transfers',
        body: [
          'Your personal data may be shared with domestic/international service providers necessary to deliver the service, such as cloud infrastructure providers, email delivery services, and error tracking (Sentry), strictly to the extent required and with appropriate technical/administrative safeguards. No data is currently shared with a third-party payment provider, as billing has not yet gone live.',
        ],
      },
      {
        heading: '6. Data Subject Rights (KVKK Article 11)',
        body: [
          'Under Article 11 of KVKK, you have the right to: learn whether your personal data is processed, request information about the processing, learn the purpose of processing and whether it is used accordingly, know the third parties to whom your data is transferred domestically/abroad, request correction of incomplete/inaccurate data, request deletion/destruction of your data, object to a result arising from processing exclusively through automated systems that is to your detriment, and claim compensation for damages arising from unlawful processing.',
          'You may exercise these rights by contacting us via your account settings.',
        ],
      },
    ],
  },
};

export const termsContent: LegalContentEntry = {
  tr: {
    title: 'Kullanım Şartları',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Hizmet Tanımı',
        body: [
          'LUCRUM Finance, kullanıcıların yatırım portföylerini (hisse senedi, TEFAS fonu, kripto para, sabit getirili varlıklar dahil) takip etmelerine, performans ve risk analizleri yapmalarına olanak tanıyan bir SaaS (Hizmet Olarak Yazılım) platformudur.',
        ],
      },
      {
        heading: '2. Yatırım Tavsiyesi Değildir',
        body: [
          'Platformda sunulan tüm veriler, analizler ve göstergeler yalnızca bilgilendirme amaçlıdır ve yatırım tavsiyesi niteliği taşımaz. Yatırım kararlarınızdan yalnızca siz sorumlusunuz.',
        ],
      },
      {
        heading: '3. Hesap Yükümlülükleri',
        body: [
          'Kullanıcı, kayıt sırasında verdiği bilgilerin doğru olduğunu, hesap şifresini gizli tutacağını ve hesabıyla ilgili tüm işlemlerden sorumlu olduğunu kabul eder.',
        ],
      },
      {
        heading: '4. Abonelik ve Ödeme',
        body: [
          'Platform, FREE/PRO/ENTERPRISE olmak üzere farklı abonelik katmanları sunar. Ücretli plan yükseltmeleri LemonSqueezy ödeme altyapısı üzerinden gerçek ücretlendirme ile işlenir. Ödeme geçmişinizi Ayarlar sayfasındaki "Ödeme Geçmişi" bölümünden görüntüleyebilirsiniz.',
        ],
      },
      {
        heading: '5. Sorumluluk Sınırlaması',
        body: [
          'Şirket, platform üzerinden sunulan verilerin (fiyat, kur, finansal gösterge vb.) üçüncü taraf kaynaklardan alındığını ve doğruluğunu garanti etmediğini beyan eder. Şirket, hizmetin kesintisiz veya hatasız olacağını taahhüt etmez.',
        ],
      },
      {
        heading: '6. Fesih',
        body: [
          'Kullanıcı, hesabını dilediği zaman kapatabilir. Şirket, bu şartların ihlali durumunda kullanıcı hesabını askıya alma veya sonlandırma hakkını saklı tutar.',
        ],
      },
    ],
  },
  en: {
    title: 'Terms of Service',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Service Description',
        body: [
          'LUCRUM Finance is a SaaS platform that allows users to track investment portfolios (including equities, TEFAS funds, cryptocurrency, and fixed-income assets), and perform performance and risk analysis.',
        ],
      },
      {
        heading: '2. Not Investment Advice',
        body: [
          'All data, analyses, and indicators provided on the platform are for informational purposes only and do not constitute investment advice. You are solely responsible for your investment decisions.',
        ],
      },
      {
        heading: '3. Account Obligations',
        body: [
          'The user warrants that the information provided during registration is accurate, agrees to keep their account password confidential, and is responsible for all activity under their account.',
        ],
      },
      {
        heading: '4. Subscription and Payment',
        body: [
          'The platform offers FREE/PRO/ENTERPRISE subscription tiers. Paid plan upgrades are processed as real charges through the LemonSqueezy payment infrastructure. You can view your payment history in the "Payment History" section of Settings.',
        ],
      },
      {
        heading: '5. Limitation of Liability',
        body: [
          'The Company states that data provided through the platform (prices, exchange rates, financial indicators, etc.) is sourced from third parties and its accuracy is not guaranteed. The Company does not warrant uninterrupted or error-free service.',
        ],
      },
      {
        heading: '6. Termination',
        body: [
          'Users may close their account at any time. The Company reserves the right to suspend or terminate a user account in case of a breach of these terms.',
        ],
      },
    ],
  },
};

export const privacyContent: LegalContentEntry = {
  tr: {
    title: 'Gizlilik Politikası',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Genel Bakış',
        body: [
          'Bu Gizlilik Politikası, LUCRUM Finance\'in kullanıcılarına ait verileri nasıl topladığını, kullandığını ve koruduğunu açıklar. KVKK Aydınlatma Metni ile birlikte okunmalıdır.',
        ],
      },
      {
        heading: '2. Toplanan Veriler',
        body: [
          'Hesap oluştururken sağladığınız bilgiler (ad, e-posta), girdiğiniz portföy/işlem verileri, ve platformu kullanırken oluşan teknik veriler (IP adresi, tarayıcı bilgisi, hata kayıtları).',
        ],
      },
      {
        heading: '3. Çerezler ve Benzer Teknolojiler',
        body: [
          'Oturumunuzu güvenli tutmak için yalnızca zorunlu (httpOnly, güvenli) bir kimlik doğrulama çerezi kullanılmaktadır. Şu an reklam veya üçüncü taraf takip amaçlı çerez kullanılmamaktadır.',
        ],
      },
      {
        heading: '4. Veri Saklama',
        body: [
          'Verileriniz, hesabınız aktif olduğu sürece ve yasal yükümlülüklerimizin gerektirdiği süre boyunca saklanır. Hesabınızı sildiğinizde, verileriniz makul bir süre içinde sistemlerimizden kaldırılır.',
        ],
      },
      {
        heading: '5. Veri Güvenliği',
        body: [
          'Şifreleriniz asla düz metin olarak saklanmaz (bcrypt ile hash\'lenir), oturum token\'ları httpOnly çerezlerde tutulur ve veritabanında hash\'lenmiş olarak saklanır.',
        ],
      },
      {
        heading: '6. İletişim',
        body: [
          'Gizlilikle ilgili sorularınız için hesap ayarlarınız üzerinden bizimle iletişime geçebilirsiniz.',
        ],
      },
    ],
  },
  en: {
    title: 'Privacy Policy',
    lastUpdated: LAST_UPDATED,
    sections: [
      {
        heading: '1. Overview',
        body: [
          'This Privacy Policy explains how LUCRUM Finance collects, uses, and protects user data. It should be read together with the KVKK Notice.',
        ],
      },
      {
        heading: '2. Data We Collect',
        body: [
          'Information you provide when creating an account (name, email), portfolio/transaction data you enter, and technical data generated while using the platform (IP address, browser information, error logs).',
        ],
      },
      {
        heading: '3. Cookies and Similar Technologies',
        body: [
          'Only a strictly necessary (httpOnly, secure) authentication cookie is used to keep your session secure. No advertising or third-party tracking cookies are currently used.',
        ],
      },
      {
        heading: '4. Data Retention',
        body: [
          'Your data is retained for as long as your account is active and for as long as required by our legal obligations. When you delete your account, your data is removed from our systems within a reasonable period.',
        ],
      },
      {
        heading: '5. Data Security',
        body: [
          'Your password is never stored in plain text (it is hashed with bcrypt), and session tokens are stored in httpOnly cookies and kept hashed in the database.',
        ],
      },
      {
        heading: '6. Contact',
        body: [
          'For privacy-related questions, you may contact us via your account settings.',
        ],
      },
    ],
  },
};

export const legalContentByKey: Record<'kvkk' | 'terms' | 'privacy', LegalContentEntry> = {
  kvkk: kvkkContent,
  terms: termsContent,
  privacy: privacyContent,
};
