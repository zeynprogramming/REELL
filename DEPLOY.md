# REEL — Դեպլոյի ուղեցույց

Նպատակը՝ ստանալ **մեկ հրապարակային հղում** (օր.՝ `https://reel.example.com`), որը ուսուցիչը կբացի իր բրաուզերում, կմուտք գործի և կփորձի ծրագիրը։

> **Կարևոր.** Այս ուղեցույցը կազմված է Docker-ով ստանդարտ դեպլոյի համար, բայց այն չի փորձարկվել իրական սերվերի վրա։ Եթե որևէ քայլի ժամանակ սխալ ստանաք, պատճենեք տերմինալի ելքը, և մենք կուղղենք։ Խնդիրների ամենահաճախ դեպքերը՝ վերջում (§7)։

---

## 0. Ի՞նչ է հիմա ծրագրում (և ինչ՝ ոչ)

| | |
|---|---|
| Աշխատում է | մուտք/դերեր, Dashboard, Recordings (upload / play / download), Academy Library, Processing Queue (իրական վիդեո-ստուգում ffprobe-ով), Consent, Settings |
| Տեսանելի է, բայց **անջատված** | **AI Content**՝ փորձնական էջ, ոչինչ չի գեներացվում և ոչ մի տվյալ չի ուղարկվում արտաքին AI-ի |
| Միայն ռեեստր | **Integrations**՝ YouTube/Slack/Classroom-ի իրական կապ չկա, ոչինչ չի հրապարակվում |

Սա պետք է ասել ուսուցչին՝ ազնվորեն։ Այն համապատասխանում է PRD-ի սահմանափակմանը՝ «չօգտագործել կեղծ հաջողության հաղորդագրություններ»։

---

## 1. Ընտրեք տարբերակը

**Տարբերակ A — սերվեր (VPS), խորհուրդ է տրվում.** Մշտական հղում, չի կախված ձեր համակարգչից։ Պետք է վճարովի սերվեր (սովորաբար մի քանի դոլար/եվրո ամսական, ստուգեք ընթացիկ գները) և միջազգային բանկային քարտ։ Կարող եք վերցնել ցանկացած Ubuntu 22.04/24.04 սերվեր, **նվազագույնը 2 ԳԲ RAM և 20 ԳԲ սկավառակ** (օր.՝ Hetzner, DigitalOcean, Vultr, Contabo, Oracle «Always Free»)։

**Տարբերակ B — ձեր համակարգչից + Cloudflare tunnel, ժամանակավոր.** Անվճար, առանց սերվերի և դոմենի, բայց հղումը աշխատում է **միայն քանի դեռ ձեր համակարգիչը միացված է** և tunnel-ը բաց է, և հասցեն փոխվում է ամեն անգամ։ Հարմար է, եթե սերվերի վճարման հնարավորություն չունեք, և ուսուցիչը կստուգի որոշակի ժամին։

---

## 2. Նախքան սկսելը՝ ձեր համակարգչում (5 րոպե)

**2.1. Մի ուղարկեք գաղտնի ֆայլերը.** Ձեր նախկին արխիվում կար `.env` ֆայլ (իրական գաղտնաբառերով), `.venv` (55 ՄԲ) և `node_modules` (145 ՄԲ)։ Սա `REEL_Final.zip`-ը դրանք չի պարունակում։ Սերվերի համար ստեղծեք **նոր** գաղտնաբառեր (§3.4), մի օգտագործեք ձեր զարգացման `.env`-ի արժեքները։

**2.2. Գործարկեք թեստերը մեկ անգամ (Docker-ով).** Ես չկարողացա դրանք գործարկել իմ միջավայրում, դրա համար ստուգեք դուք.

```bash
cd REEL_Final
docker compose build backend
docker compose run --rm --no-deps backend pytest -q
```

Սպասվող արդյունք՝ ամեն ինչ `passed`։ Եթե ինչ-որ թեստ ձախողվի, ուղարկեք ելքը՝ ուղղելու համար։ Սա նաև լավ ցուցանիշ է ուսուցչին՝ «ծրագիրը թեստավորված է»։

**2.3. Ստուգեք, որ վեբ հավելվածը հավաքվում է** (կամ պարզապես սպասեք §3.6-ին, որտեղ այն հավաքվում է սերվերում).

```bash
cd frontend && npm ci && npm run build
```

---

## 3. Տարբերակ A — VPS-ի վրա (քայլ առ քայլ)

### 3.1. Ստեղծեք սերվեր և միացեք

Ընտրեք **Ubuntu 24.04**, ավելացրեք ձեր SSH բանալին (կամ գաղտնաբառ), և գրեք սերվերի IP-ն։ Միացեք.

```bash
ssh root@ՁԵՐ_IP
```

### 3.2. Տեղադրեք Docker-ը և փակեք ավելորդ պորտերը

```bash
apt update && apt install -y ca-certificates curl ufw unzip
curl -fsSL https://get.docker.com | sh

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
```

Բազան և Redis-ը արդեն հասանելի չեն դրսից (production compose-ը դրանց պորտեր չի բացում)։

Եթե սերվերը ունի 2 ԳԲ RAM, ավելացրեք swap, որպեսզի վեբ հավելվածի հավաքումը չընդհատվի.

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### 3.3. Հասցե (domain)

Երկու ճանապարհ.
- **Ունեք դոմեն.** DNS-ում ավելացրեք `A` գրառում՝ `reel` → ձեր IP-ն (այսինքն `reel.ձեր-դոմեն.am`)։ Սպասեք մի քանի րոպե։
- **Դոմեն չունեք.** Օգտագործեք անվճար `sslip.io`. եթե IP-ն `203.0.113.7` է, ձեր հասցեն `203-0-113-7.sslip.io` է (կետերը՝ գծիկներով)։ Սա աշխատում է ավտոմատ։

### 3.4. Բեռնեք նախագիծը սերվեր

Ձեր **համակարգչից** (ոչ սերվերից).

```bash
scp REEL_Final.zip root@ՁԵՐ_IP:~/
```

Սերվերում.

```bash
cd ~ && unzip -q REEL_Final.zip && mv REEL_Final reel && cd reel
```

### 3.5. Լրացրեք գաղտնի կարգավորումները

```bash
cp .env.prod.example .env.prod
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env.prod
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env.prod
chmod 600 .env.prod
nano .env.prod
```

`nano`-ում լրացրեք միայն սրանք (Ctrl+O, Enter՝ պահելու, Ctrl+X՝ դուրս գալու).
- `DOMAIN=` ձեր հասցեն (օր.՝ `203-0-113-7.sslip.io`), առանց `https://`։
- `BOOTSTRAP_ADMIN_EMAIL=` ձեր email-ը (սա ձեր admin մուտքն է)։
- `BOOTSTRAP_ADMIN_PASSWORD=` **նոր** երկար գաղտնաբառ (առնվազն 10 նիշ)։

### 3.6. Գործարկեք

```bash
./scripts/prod.sh up -d --build
```

Առաջին անգամ սա տևում է 5–10 րոպե։ Հետևեք.

```bash
./scripts/prod.sh ps               # բոլորը պետք է լինեն "running" / "healthy"
./scripts/prod.sh logs -f web      # Ctrl+C՝ դուրս գալու
```

Բացեք `https://ՁԵՐ_ՀԱՍՑԵՆ` բրաուզերում. կտեսնեք մուտքի էջը։ Մուտք գործեք `BOOTSTRAP_ADMIN_EMAIL`-ով։

### 3.7. Ավելացրեք demo տվյալներ (խորհուրդ է տրվում)

Դատարկ ծրագիրը ուսուցչին քիչ բան ցույց կտա։ Այս հրամանը ստեղծում է իրական 20 վայրկյանոց թեստային վիդեո, վավերացնում այն worker-ի կոդով և ավելացնում մի քանի օրինակ գրառում.

```bash
./scripts/prod.sh exec backend python -m app.seed_demo
```

Սպասվող ելք՝ `Demo data created. Validation job finished: completed.` Այն կարելի է գործարկել կրկին՝ անվտանգ է։

### 3.8. Ստեղծեք ուսուցչի հաշիվ

Մուտք գործեք որպես admin → **Settings** → «Create user».
- **Viewer**՝ կարող է միայն դիտել (անվտանգ, ոչինչ չի կարող փչացնել)։
- **Editor**՝ կարող է բեռնել, ջնջել, գործարկել job-եր (ուսուցիչը կարող է լրիվ փորձել, բայց կարող է նաև ջնջել demo-ն)։

Խորհուրդ՝ **Editor**, որպեսզի փորձի upload-ը, իսկ demo-ն հետո վերականգնվում է §3.7-ով։ Upload-ի սահմանը 200 ՄԲ է (`MAX_UPLOAD_MB`)։

Անմիջապես փոխեք ձեր admin գաղտնաբառը **Settings → My account**-ում։ Հետո կարող եք `.env.prod`-ից ջնջել `BOOTSTRAP_ADMIN_PASSWORD`-ի արժեքը։

---

## 4. Տարբերակ B — ձեր համակարգչից (Cloudflare tunnel)

Պահանջվում է Docker և `cloudflared` ([տեղադրման հրահանգ](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/))։

```bash
cd REEL_Final
cp .env.prod.example .env.prod
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env.prod
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env.prod
nano .env.prod          # DOMAIN=:80   (սա նշանակում է՝ առանց HTTPS, tunnel-ը ինքը կտա HTTPS)
                        # + BOOTSTRAP_ADMIN_EMAIL և BOOTSTRAP_ADMIN_PASSWORD
./scripts/prod.sh up -d --build
./scripts/prod.sh exec backend python -m app.seed_demo
cloudflared tunnel --url http://localhost:80
```

Տերմինալում կերևա `https://ինչ-որ-բան.trycloudflare.com` հասցե. սա է հղումը։ **Պահեք տերմինալը բաց** և համակարգիչը միացված, քանի դեռ ուսուցիչը ստուգում է։ Սա ժամանակավոր լուծում է, Cloudflare-ը չի երաշխավորում աշխատանքի ժամանակը։

---

## 5. Ինչ ուղարկել ուսուցչին

> **REEL — Video Automation Platform**
> Հղում՝ `https://ՁԵՐ_ՀԱՍՑԵՆ`
> Email՝ `teacher@…` Գաղտնաբառ՝ `…`
>
> Ինչ փորձել (≈5 րոպե).
> 1. Dashboard՝ վիճակագրական քարտեր, վերջին ձայնագրություններ։
> 2. **Recordings** → վերբեռնել փոքր MP4 (մինչև 200 ՄԲ) → սեղմել **Play**, **Download**, **Validate**։
> 3. **Processing Queue** → job-ի կարգավիճակը (queued → processing → completed) և արդյունքը (ռեզոլյուցիա, կոդեկ, տևողություն)։
> 4. **Academy Library** → դիտել վիդեոն։
> 5. **Consent Management**, **Integrations**, **Settings** (դերեր, audit log՝ admin-ի համար)։
> 6. Dark/Light թեմա (վերևի աջ անկյուն)։
>
> Ի գիտություն. **AI Content** բաժինը տեսանելի է, բայց միտումնավոր անջատված է (փորձնական)։ **Integrations**-ը միայն ռեեստր է, YouTube/Slack/Classroom-ի իրական կապ չկա։ Պատճառը՝ ուսանողական տվյալների գաղտնիություն և ժամանակի սահմանափակում։

---

## 6. Ամենօրյա հրամաններ

```bash
./scripts/prod.sh ps                      # վիճակ
./scripts/prod.sh logs -f backend         # լոգեր (backend / worker / web / db)
./scripts/prod.sh restart backend         # վերագործարկել մեկ ծառայություն
./scripts/prod.sh up -d --build           # թարմացնել կոդից հետո (նոր zip-ը բացելուց հետո)
./scripts/prod.sh down                    # կանգնեցնել (տվյալները պահպանվում են)
./scripts/backup.sh                       # պահուստ՝ backups/ թղթապանակ (բազա + վիդեոներ)
```

**Զգուշացում.** `./scripts/prod.sh down -v` **ջնջում է** բազան և բոլոր բեռնված վիդեոները։ Մի օգտագործեք, եթե տվյալները պետք են։

Երբ գնահատումը ավարտվի և սերվերը այլևս պետք չէ, ջնջեք այն provider-ի էջից, այլապես վճարումը կշարունակվի։

---

## 7. Խնդիրներ և լուծումներ

| Ախտանիշ | Հավանական պատճառ → ինչ անել |
|---|---|
| Բրաուզերը ասում է «անապահով» / կապը չի հաստատվում | DNS-ը դեռ չի թարմացվել, կամ 80/443 պորտերը փակ են։ Ստուգեք `ufw status`, և որ `DOMAIN`-ը ճիշտ է։ Լոգեր՝ `./scripts/prod.sh logs web` (տեսնում եք certificate-ի սխալները)։ |
| 502 / «Bad Gateway» | Backend-ը դեռ չի բարձրացել կամ ընկել է։ `./scripts/prod.sh ps`, հետո `./scripts/prod.sh logs backend`։ |
| Backend-ը չի մեկնարկում, լոգում՝ `SECRET_KEY` | `.env.prod`-ում `SECRET_KEY`-ը դատարկ է կամ <32 նիշ։ |
| `docker compose` գանգատվում է «Set … in .env.prod» | Բաց թողած արժեք։ Լրացրեք և կրկնեք։ |
| Մուտքը չի աշխատում | Գաղտնաբառը ճիշտ չէ։ 5 սխալ փորձից հետո մուտքը 15 րոպե արգելափակվում է (անվտանգություն)։ Ստուգեք՝ արդյոք առաջին admin-ը ստեղծվել է. `./scripts/prod.sh logs backend | grep -i administrator`։ Եթե չի ստեղծվել (օրինակ՝ `BOOTSTRAP_*` դատարկ էր առաջին մեկնարկին), լրացրեք և `./scripts/prod.sh restart backend` (աշխատում է միայն եթե օգտատերեր դեռ չկան)։ |
| Upload-ը ձախողվում է | 200 ՄԲ-ից մեծ ֆայլ, կամ ոչ MP4/MOV/WebM/MKV/AVI։ Սխալի հաղորդագրությունը ցույց է տալիս պատճառը։ |
| Processing Queue-ում «No worker is running» | `./scripts/prod.sh ps` → `worker`-ը ընկած է։ `./scripts/prod.sh logs worker`, հետո `restart worker`։ |
| Հավաքումը («build») ընդհատվում է «Killed» | Հիշողությունը բավարար չէ → ավելացրեք swap (§3.2) կամ վերցրեք 4 ԳԲ սերվեր։ |
| Թեստերը ձախողվում են §2.2-ում | Ուղարկեք ելքը։ |
