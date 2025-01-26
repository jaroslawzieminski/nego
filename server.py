from flask import Flask, jsonify, request, render_template_string, redirect, url_for
from flask_socketio import SocketIO, emit
import time
import uuid
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, async_mode='asyncio')

# Dane aukcji
auction = {
    "item": "Zakup usługi X",
    "lowestBid": None,
    "bids": [],
    "startTime": None,  # Start aukcji (czas w formacie unix)
    "duration": 300,  # 5 minut
    "minIncrement": 5,
    "startingPrice": 1000,
    "isActive": True
}

# Lista zaproszonych użytkowników: token -> imię użytkownika
invited_users = {}

# Szablon Admina z podglądem aukcji
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Panel Administracyjny</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f4f4; font-family: Arial, sans-serif; }
        .container { margin-top: 40px; max-width: 800px; }
        h1 { text-align: center; color: #333; }
        .card { border: none; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .btn-success { margin-top: 10px; }
        .bid-list { max-height: 300px; overflow-y: scroll; }
    </style>
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>Panel Administracyjny</h1>
        <div class="card p-4 mb-4">
            <form method="POST" action="/admin">
                <div class="mb-3">
                    <label>Przedmiot aukcji</label>
                    <input type="text" name="item" class="form-control" value="{{ auction.item }}">
                </div>
                <div class="mb-3">
                    <label>Czas trwania aukcji (sekundy)</label>
                    <input type="number" name="duration" class="form-control" value="{{ auction.duration }}">
                </div>
                <div class="mb-3">
                    <label>Data i godzina startu aukcji</label>
                    <input type="datetime-local" name="startTime" class="form-control" required>
                </div>
                <div class="mb-3">
                    <label>Minimalne postąpienie (zł)</label>
                    <input type="number" name="minIncrement" class="form-control" value="{{ auction.minIncrement }}">
                </div>
                <div class="mb-3">
                    <label>Cena wywoławcza (zł)</label>
                    <input type="number" name="startingPrice" class="form-control" value="{{ auction.startingPrice }}">
                </div>
                <button type="submit" class="btn btn-primary w-100">Zaktualizuj aukcję</button>
            </form>
            <button onclick="resetAuction()" class="btn btn-danger w-100 mt-3">Zresetuj Aukcję</button>
            <button onclick="endAuction()" class="btn btn-warning w-100 mt-3">Zakończ Aukcję</button>
        </div>
        <div class="card p-4 mb-4">
            <h4>Ostatnie Oferty</h4>
            <ul class="list-group bid-list" id="bidList">
                {% for bid in auction.bids %}
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        {{ bid.bidder }}: {{ bid.price }} zł
                    </li>
                {% endfor %}
            </ul>
        </div>
        <div class="card p-4">
            <h4>Generuj Zaproszenie</h4>
            <input type="text" id="invite_user" placeholder="Imię użytkownika" class="form-control mb-2">
            <button onclick="generateInvitation()" class="btn btn-success w-100">Wygeneruj i Kopiuj Link</button>
        </div>
        <div class="card p-4 mt-3">
            <h4>Lista Zaproszonych Użytkowników</h4>
            <ul class="list-group">
                {% for token, user in invited_users.items() %}
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        {{ user }}
                        <input type="text" value="http://127.0.0.1:4000/auction/{{ token }}" class="form-control-sm" readonly>
                    </li>
                {% endfor %}
            </ul>
        </div>
    </div>
    <script>
        const socket = io();
        socket.on('new_bid', (data) => {
            const bidList = document.getElementById('bidList');
            const newBid = document.createElement('li');
            newBid.className = 'list-group-item d-flex justify-content-between align-items-center';
            newBid.textContent = `${data.bidder}: ${data.price} zł`;
            bidList.prepend(newBid);
        });

        function generateInvitation() {
            const userName = document.getElementById("invite_user").value;
            if (!userName) {
                alert("Podaj imię użytkownika.");
                return;
            }
            fetch("/send_invitation", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({user_name: userName})
            }).then(response => response.json())
              .then(data => {
                  if (data.error) {
                      alert(data.error);
                  } else {
                      alert("Link skopiowany do schowka: " + data.link);
                      navigator.clipboard.writeText(data.link);
                      location.reload();
                  }
              });
        }

        function resetAuction() {
            fetch("/reset_auction", {
                method: "POST"
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert("Aukcja została zresetowana.");
                      location.reload();
                  } else {
                      alert("Wystąpił problem podczas resetowania aukcji.");
                  }
              });
        }

        function endAuction() {
            fetch("/end_auction", {
                method: "POST"
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert("Aukcja została zakończona.");
                      location.reload();
                  } else {
                      alert("Wystąpił problem podczas kończenia aukcji.");
                  }
              });
        }
    </script>
</body>
</html>
"""

USER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Aukcja</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f4f4; font-family: Arial, sans-serif; }
        .container { margin-top: 40px; max-width: 700px; text-align: center; }
        .info-box { padding: 20px; border-radius: 8px; background-color: #e7f5ff; margin-bottom: 20px; }
    </style>
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>Witaj, {{ user_name }}!</h1>
        <div class="info-box">
            <h3>{{ auction.item }}</h3>
            <p id="lowestBid">Najniższa oferta: {{ auction.lowestBid.price if auction.lowestBid else 'Brak ofert' }} zł</p>
            <p>Cena wywoławcza: {{ auction.startingPrice }} zł</p>
            <p id="timer">Pozostały czas: --:--</p>
        </div>
        <p style="margin-top: 20px;">Złożenie oferty jest równoznaczne z akceptacją <a href="/terms" target="_blank">regulaminu</a>.</p>
        <input type="number" id="bidInput" class="form-control w-50 mx-auto" placeholder="Twoja oferta">
        <button class="btn btn-primary mt-3" onclick="sendBid()">Złóż ofertę</button>
    </div>
    <script>
        const socket = io();

        let auctionStartTime = {{ auction.startTime }};
        let auctionEndTime = auctionStartTime + {{ auction.duration }};

        function updateTimer() {
            const now = Math.floor(Date.now() / 1000);
            if (now < auctionStartTime) {
                const remainingStart = auctionStartTime - now;
                const minutes = Math.floor(remainingStart / 60).toString().padStart(2, '0');
                const seconds = Math.floor(remainingStart % 60).toString().padStart(2, '0');
                document.getElementById('timer').innerText = `Aukcja startuje za: ${minutes}:${seconds}`;
                document.querySelector('button').disabled = true;
            } else {
                const remaining = auctionEndTime - now;
                if (remaining <= 0) {
                    document.getElementById('timer').innerText = 'Aukcja zakończona';
                    document.querySelector('button').disabled = true;
                } else {
                    const minutes = Math.floor(remaining / 60).toString().padStart(2, '0');
                    const seconds = Math.floor(remaining % 60).toString().padStart(2, '0');
                    document.getElementById('timer').innerText = `Pozostały czas: ${minutes}:${seconds}`;
                    document.querySelector('button').disabled = false;
                }
            }
        }
        setInterval(updateTimer, 1000);
        updateTimer();

        function sendBid() {
            const price = document.getElementById('bidInput').value;
            fetch('/api/bids', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({price: parseFloat(price), token: "{{ token }}"})
            }).then(response => response.json())
              .then(data => {
                  if (data.error) {
                      alert(data.error);
                  } else {
                      auctionEndTime = Math.floor(Date.now() / 1000) + {{ auction.duration }};
                  }
              });
        }

        socket.on('new_bid', (data) => {
            document.getElementById('lowestBid').innerText = `Najniższa oferta: ${data.price} zł`;
            auctionEndTime = Math.floor(Date.now() / 1000) + data.newDuration;
        });
    </script>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        auction['item'] = request.form['item']
        auction['minIncrement'] = int(request.form['minIncrement'])
        auction['startingPrice'] = int(request.form['startingPrice'])
        auction['duration'] = int(request.form['duration'])
        start_time_str = request.form['startTime']
        try:
            auction['startTime'] = int(datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M").timestamp())
        except ValueError:
            return "Nieprawidłowy format daty. Użyj formatu: RRRR-MM-DDTHH:MM (wymuszane przez przeglądarkę).", 400
    return render_template_string(ADMIN_TEMPLATE, auction=auction, invited_users=invited_users)

@app.route('/reset_auction', methods=['POST'])
def reset_auction():
    auction['lowestBid'] = None
    auction['bids'] = []
    auction['startTime'] = None
    auction['isActive'] = True
    socketio.emit('auction_reset', {})
    return jsonify({"success": True})

@app.route('/end_auction', methods=['POST'])
def end_auction():
    auction['isActive'] = False
    socketio.emit('auction_ended', {})
    return jsonify({"success": True})

@app.route('/send_invitation', methods=['POST'])
def send_invitation():
    user_name = request.json.get("user_name")
    if not user_name:
        return jsonify({"error": "Brak imię użytkownika."}), 400
    token = str(uuid.uuid4())
    invited_users[token] = user_name
    link = f"http://127.0.0.1:4000/auction/{token}"
    return jsonify({"link": link})

@app.route('/terms')
def terms():
    return """<h1>Regulamin uczestnika aukcji w aplikacji</h1>
<p>1. Postanowienia ogólne</p>
<p>1.1. Niniejszy regulamin określa zasady uczestnictwa w aukcjach organizowanych za pośrednictwem aplikacji [Nazwa Aplikacji] (dalej: "Aplikacja").</p>
<p>1.2. Właścicielem i operatorem Aplikacji jest [Nazwa Firmy], z siedzibą w [adres firmy], NIP: [numer NIP], REGON: [numer REGON].</p>
<p>1.3. Uczestnik, korzystając z tokenu w celu wzięcia udziału w aukcji, akceptuje postanowienia niniejszego regulaminu.</p>
<p>2. Uczestnictwo w aukcjach</p>
<p>2.1. Uczestnictwo w aukcjach jest możliwe wyłącznie dla osób, które ukończyły 18 lat lub posiadają zgodę opiekuna prawnego.</p>
<p>2.2. Każda oferta złożona w trakcie aukcji za pośrednictwem Aplikacji jest wiążąca przez okres 30 dni od zakończenia aukcji, chyba że w regulaminie danej aukcji określono inaczej.</p>
<p>2.3. Zamawiający ma prawo przerwać lub odwołać aukcję w dowolnym momencie przed jej zakończeniem, bez podania przyczyny. W przypadku przerwania lub odwołania aukcji wszystkie oferty złożone do tego momentu przestają być wiążące.</p>
<p>2.4. Uczestnik zobowiązuje się do podania prawdziwych danych wymaganych w ramach procesu korzystania z tokenu.</p>
<p>2.5. Uczestnik jest zobowiązany do zabezpieczenia tokenu przed dostępem osób nieuprawnionych. W przypadku podejrzenia, że osoba nieuprawniona próbowała skorzystać z tokenu, uczestnik powinien niezwłocznie poinformować o tym Właściciela Aplikacji.</p>
<p>3. Obowiązki uczestnika</p>
<p>3.1. Uczestnik ponosi odpowiedzialność za złożone oferty i zobowiązuje się do realizacji transakcji w przypadku przyjęcia jego oferty przez Zamawiającego.</p>
<p>3.2. Złożenie oferty w trakcie aukcji za pośrednictwem Aplikacji oznacza pełną akceptację niniejszego regulaminu oraz jego wszystkich postanowień.</p>
<p>3.3. Zabrania się składania ofert w celu destabilizacji aukcji lub w innych celach niezgodnych z przeznaczeniem Aplikacji.</p>
<p>4. Zasady wiążącej oferty</p>
<p>4.1. Oferta złożona przez uczestnika jest wiążąca przez okres 30 dni od momentu zakończenia aukcji, niezależnie od wyniku.</p>
<p>4.2. W przypadku wyboru oferty przez Zamawiającego uczestnik zobowiązany jest do jej realizacji zgodnie z warunkami określonymi w aukcji.</p>
<p>5. Odpowiedzialność</p>
<p>5.1. Właściciel Aplikacji nie ponosi odpowiedzialności za treści wprowadzone przez uczestników ani za niewywiązanie się z zobowiązań wynikających z aukcji.</p>
<p>5.2. Właściciel Aplikacji zastrzega sobie prawo do zablokowania możliwości udziału w aukcjach w przypadku naruszenia regulaminu.</p>
<p>5.3. Właściciel Aplikacji nie ponosi odpowiedzialności za szkody wynikające z nieautoryzowanego użycia tokenu przez osoby nieuprawnione, chyba że uczestnik niezwłocznie zgłosił takie podejrzenie zgodnie z pkt. 2.5.</p>
<p>6. Prywatność i dane osobowe</p>
<p>6.1. Właściciel Aplikacji przetwarza dane osobowe uczestników zgodnie z obowiązującymi przepisami prawa oraz polityką prywatności.</p>
<p>6.2. Szczegółowe informacje na temat przetwarzania danych osobowych znajdują się w Polityce Prywatności dostępnej pod adresem [link].</p>
<p>7. Postanowienia końcowe</p>
<p>7.1. Właściciel Aplikacji zastrzega sobie prawo do zmiany niniejszego regulaminu. O wszelkich zmianach uczestnicy zostaną poinformowani z odpowiednim wyprzedzeniem.</p>
<p>7.2. Wszelkie spory związane z korzystaniem z Aplikacji i udziałem w aukcjach będą rozstrzygane przez sąd właściwy dla siedziby właściciela.</p>
<p>Kontakt</p>
<p>W przypadku pytań lub wątpliwości prosimy o kontakt pod adresem e-mail: [adres e-mail] lub telefonicznie: [numer telefonu].</p>
<p>Data wejścia w życie regulaminu: [data].</p>
"""""

@app.route('/auction/<token>')
def auction_view(token):
    if token not in invited_users:
        return "Nieprawidłowy token.", 403
    return render_template_string(USER_TEMPLATE, auction=auction, user_name=invited_users[token], token=token)

@app.route('/api/bids', methods=['POST'])
def new_bid():
    data = request.json
    price = data.get("price")
    token = data.get("token")
    now = time.time()

    if not price or price <= 0 or token not in invited_users:
        return jsonify({"error": "Nieprawidłowe dane."}), 400

    if auction['startTime'] is None or now < auction['startTime']:
        return jsonify({"error": "Aukcja jeszcze się nie rozpoczęła."}), 400

    if not auction['isActive']:
        return jsonify({"error": "Aukcja została zakończona."}), 400

    if auction['lowestBid'] and (auction['lowestBid']['price'] - price) < auction['minIncrement']:
        return jsonify({"error": f"Oferta musi być niższa o {auction['minIncrement']} zł."}), 400

    auction['lowestBid'] = {"price": price, "bidder": invited_users[token]}
    auction['bids'].append({"price": price, "bidder": invited_users[token]})

    socketio.emit('new_bid', {"price": price, "bidder": invited_users[token], "newDuration": auction['duration']})

    return jsonify({"success": True, "lowestBid": price})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.getenv("PORT", 4000)))

