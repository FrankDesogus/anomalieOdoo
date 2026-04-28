# Manuale operativo – Tool controllo presenze Odoo

## Scopo

Questo tool verifica automaticamente le anomalie di presenza registrate su Odoo e genera report utili per il controllo operativo delle timbrature.

Le verifiche principali riguardano:

- assenza di check-in
- ingresso in ritardo
- pausa pranzo senza rientro
- rientro tardivo dalla pausa pranzo
- chiusura automatica tardiva
- assenza totale di presenze nella giornata

---

## Avvio del programma

Il punto di ingresso del progetto è:

```bash
python main.py
```

Questo comando equivale a:

```bash
python main.py --mode ops
```

ed esegue il controllo operativo standard su oggi + ieri.

---

## Modalità disponibili

## 1. Modalità operativa (OPS)

Controlla automaticamente le anomalie recenti.

### Comando base

```bash
python main.py --mode ops
```

### Con storico personalizzato

```bash
python main.py --mode ops --lookback-days 3
```

Controlla oggi e i 3 giorni precedenti.

Uso consigliato: controllo giornaliero aziendale.

---

## 2. Modalità giorno singolo

Genera il report per una data specifica.

### Comando

```bash
python main.py --mode day --day 2026-01-20
```

### Con controllo anche del giorno precedente

```bash
python main.py --mode day --day 2026-01-20 --also-prev
```

Uso consigliato: verifiche puntuali o controlli retroattivi.

---

## 3. Modalità mensile

Genera il report completo di un mese.

### Comando

```bash
python main.py --mode month --month 2026-01
```

Uso consigliato: chiusure mensili e controlli amministrativi.

---

## Opzioni aggiuntive

## Invio email automatico

```bash
--send-mail
```

Esempio:

```bash
python main.py --mode ops --send-mail
```

Funziona solo se nel file `config.yaml` è presente:

```yaml
mail:
  enabled: true
```

---

## Disattivazione deduplica

```bash
--no-dedup
```

Esempio:

```bash
python main.py --mode ops --no-dedup
```

Serve per rigenerare o reinviare report già prodotti.

Normalmente la deduplica evita duplicati nei controlli.

---

## Elenco anomalie rilevate

Il sistema può generare i seguenti alert:

### NO_CHECKIN_BY_0900
Nessun ingresso registrato entro le 09:00.

### LATE_CHECKIN
Ingresso registrato in ritardo.

### LUNCH_NO_RETURN
Nessun rientro dalla pausa pranzo.

### LUNCH_LATE_RETURN
Rientro tardivo dalla pausa pranzo.

### AUTO_CLOSE_LATE
Chiusura automatica tardiva della presenza.

### NO_ATTENDANCE_ALL_DAY
Nessuna presenza registrata durante tutta la giornata.

---

## Configurazione

Il file principale di configurazione è:

```text
config.yaml
```

Contiene:

- connessione Odoo
- parametri di controllo
- impostazioni email
- gestione deduplica

---

## Nota di sicurezza

Attualmente la password Odoo risulta salvata in chiaro nel file `config.yaml`.

È fortemente consigliato spostarla in:

- variabili d’ambiente
oppure
- file `.env` escluso dal versionamento Git

per evitare problemi di sicurezza.

---

## Uso consigliato in azienda

### Ogni giorno

```bash
python main.py --mode ops
```

### Controllo straordinario su una data

```bash
python main.py --mode day --day AAAA-MM-GG
```

### Chiusura mensile

```bash
python main.py --mode month --month AAAA-MM
```

Questo garantisce un monitoraggio semplice, ripetibile e affidabile delle presenze aziendali.

