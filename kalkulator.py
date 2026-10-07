import json
import re
import os
import cloudscraper
from bs4 import BeautifulSoup
import streamlit as st

# =============================================================================
# WCZYTYWANIE PRODUKTÓW Z PLIKU JSON
# =============================================================================
@st.cache_data(ttl=60)
def load_products_from_json(filename="produkty.json") -> dict:
    """Wczytuje strukturę kategorii i produktów z pliku JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Błąd podczas odczytu pliku {filename}: {e}")
    return {}

# =============================================================================
# UNIWERSALNY EKSTRAKTOR DANYCH (JSON-LD, META PIXEL, DATALAYER)
# =============================================================================
def extract_product_data(html_content: str) -> dict | None:
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. STRATEGIA A: JSON-LD (Schema.org)
    for script in soup.find_all('script', type='application/ld+json'):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else data.get('@graph', [data])
                
            for item in items:
                if isinstance(item, dict) and item.get('@type') in ['Product', 'IndividualProduct']:
                    name = item.get('name')
                    offers = item.get('offers', {})
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    
                    price = offers.get('price') or offers.get('lowPrice')
                    
                    if price and name:
                        return {
                            "name": str(name).strip(),
                            "price": float(str(price).replace(',', '.')),
                            "source": "JSON-LD (Schema.org)"
                        }
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # 2. STRATEGIA B: Meta Pixel (Facebook)
    pixel_match = re.search(
        r"fbq\s*\(\s*['\"]track['\"]\s*,\s*['\"]ViewContent['\"]\s*,\s*(\{.*?\})\s*[\),]", 
        html_content, 
        re.DOTALL
    )
    if pixel_match:
        pixel_data = pixel_match.group(1)
        price_match = re.search(r'["\']?value["\']?\s*:\s*["\']?([\d\.,]+)["\']?', pixel_data)
        name_match = re.search(r'["\']?content_name["\']?\s*:\s*["\']([^"\']+)["\']', pixel_data)
        
        if price_match:
            price_val = price_match.group(1).replace(',', '.')
            name_val = name_match.group(1) if name_match else "Nieznany produkt"
            try:
                return {
                    "name": name_val.strip(),
                    "price": float(price_val),
                    "source": "Meta Pixel"
                }
            except ValueError:
                pass

    # 3. STRATEGIA C: Google Tag Manager (dataLayer)
    datalayer_matches = re.findall(r'dataLayer\.push\s*\(\s*(\{.*?\})\s*\)', html_content, re.DOTALL)
    for dl_text in datalayer_matches:
        name_match = re.search(r'["\']?(?:item_name|content_name|name)["\']?\s*:\s*["\']([^"\']+)["\']', dl_text)
        price_match = re.search(r'["\']?(?:price|value)["\']?\s*:\s*["\']?([\d\.,]+)["\']?', dl_text)
        
        if price_match and name_match:
            try:
                return {
                    "name": name_match.group(1).strip(),
                    "price": float(price_match.group(1).replace(',', '.')),
                    "source": "Google Tag Manager (dataLayer)"
                }
            except ValueError:
                continue

    return None


def fetch_product_info(url: str) -> tuple[dict | None, str | None]:
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        response = scraper.get(url, timeout=12)
        
        if response.status_code != 200:
            return None, f"Nie udało się połączyć ze stroną (Kod HTTP: {response.status_code})"
        
        data = extract_product_data(response.text)
        if data:
            return data, None
        return None, "Nie odnaleziono struktury ceny na podanej stronie."
    except Exception as e:
        return None, f"Błąd połączenia: {e}"


# =============================================================================
# INTERFEJS UŻYTKOWNIKA (STREAMLIT)
# =============================================================================
st.set_page_config(page_title="Kalkulator Budowlany", page_icon="🏗️", layout="wide")

# Inicjalizacja listy koszyka / kosztorysu w stanie sesji
if "kosztorys" not in st.session_state:
    st.session_state.kosztorys = []

st.title("🏗️ Kalkulator Kosztów Budowlanych")
st.write("Dodawaj produkty z bazy lub własnych linków do kosztorysu, podawaj ilości i obliczaj łączny koszt inwestycji.")

# Wczytanie produktów z pliku JSON
raw_catalog = load_products_from_json()

# Budowanie pełnego katalogu z opcją własnego linku
PRODUCTS_CATALOG = {
    "📌 Własny link": {
        "Wklej własny adres URL...": ""
    }
}
PRODUCTS_CATALOG.update(raw_catalog)

# -----------------------------------------------------------------------------
# SEKCJA 1: DODAWANIE PRODUKTU DO KOSZTORYSU
# -----------------------------------------------------------------------------
st.subheader("1. Dodaj produkt do kosztorysu")

col_cat, col_prod, col_qty = st.columns([2, 3, 1])

with col_cat:
    categories = list(PRODUCTS_CATALOG.keys())
    selected_category = st.selectbox("Kategoria:", categories)

with col_prod:
    available_products = PRODUCTS_CATALOG.get(selected_category, {})
    product_names = list(available_products.keys())
    selected_product = st.selectbox("Produkt:", product_names) if product_names else None

with col_qty:
    quantity = st.number_input("Ilość (szt. / op.):", min_value=1, value=10, step=1)

# Pasek na URL jeśli wybrano opcję własnego linku
if selected_category == "📌 Własny link" or selected_product == "Wklej własny adres URL...":
    product_url = st.text_input("Adres URL strony produktu:", placeholder="https://sklep.pl/produkt-123")
else:
    product_url = available_products.get(selected_product, "")
    st.text_input("Adres URL strony produktu:", value=product_url, disabled=True)

# Przycisk dodawania towaru
if st.button("➕ Dodaj do kosztorysu", type="primary"):
    if not product_url or not product_url.startswith("http"):
        st.warning("Wprowadź prawidłowy adres URL rozpoczynający się od http:// lub https://")
    else:
        with st.spinner("Pobieranie aktualnej ceny produktu ze sklepu..."):
            data, error = fetch_product_info(product_url)
        
        if error:
            st.error(error)
        else:
            unit_price = data["price"]
            display_name = selected_product if selected_category != "📌 Własny link" else data["name"]
            data_source = data["source"]
            total_item_price = unit_price * quantity
            
            # Dodanie pozycji do listy kosztorysu w sesji
            new_item = {
                "category": selected_category,
                "name": display_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_item_price,
                "source": data_source,
                "url": product_url
            }
            st.session_state.kosztorys.append(new_item)
            st.success(f"Dodano do kosztorysu: **{display_name}** ({quantity} szt. × {unit_price:.2f} PLN)")
            st.rerun()

st.markdown("---")

# -----------------------------------------------------------------------------
# SEKCJA 2: ROZBICIE KOSZTÓW NA POSZCZEGÓLNE TOWARY (ZESTAWIENIE)
# -----------------------------------------------------------------------------
st.subheader("2. Zestawienie i rozbicie kosztów na poszczególne towary")

if not st.session_state.kosztorys:
    st.info("Kosztorys jest obecnie pusty. Wybierz i dodaj pierwsze produkty powyżej.")
else:
    # Tabela z rozbiciem towarów
    header_cols = st.columns([1.5, 3, 1, 1.5, 1.5, 1])
    header_cols[0].markdown("**Kategoria**")
    header_cols[1].markdown("**Nazwa towaru**")
    header_cols[2].markdown("**Ilość**")
    header_cols[3].markdown("**Cena jedn. [PLN]**")
    header_cols[4].markdown("**Wartość [PLN]**")
    header_cols[5].markdown("**Akcja**")

    st.markdown("---")

    to_remove = None
    for index, item in enumerate(st.session_state.kosztorys):
        cols = st.columns([1.5, 3, 1, 1.5, 1.5, 1])
        cols[0].write(item["category"])
        cols[1].markdown(f"[{item['name']}]({item['url']})")
        cols[2].write(f"{item['quantity']}")
        cols[3].write(f"{item['unit_price']:.2f}")
        cols[4].write(f"**{item['total_price']:.2f}**")
        if cols[5].button("❌ Usuń", key=f"del_{index}"):
            to_remove = index

    if to_remove is not None:
        st.session_state.kosztorys.pop(to_remove)
        st.rerun()

    st.markdown("---")
    if st.button("🗑️ Wyczyść cały kosztorys"):
        st.session_state.kosztorys = []
        st.rerun()

    # -----------------------------------------------------------------------------
    # SEKCJA 3: KALKULACJA CAŁKOWITA Z ROBOCIZNĄ
    # -----------------------------------------------------------------------------
    st.subheader("3. Podsumowanie całego kosztorysu")

    col_labor, col_spacer = st.columns([2, 2])
    with col_labor:
        labor_cost = st.number_input("Łączny koszt robocizny / montażu (PLN):", min_value=0.0, value=500.0, step=50.0)

    # Obliczenia końcowe
    total_materials = sum(item["total_price"] for item in st.session_state.kosztorys)
    total_investment = total_materials + labor_cost

    res1, res2, res3 = st.columns(3)
    res1.metric("Suma materiałów", f"{total_materials:.2f} PLN")
    res2.metric("Koszt robocizny", f"{labor_cost:.2f} PLN")
    res3.metric("ŁĄCZNY KOSZT INWESTYCJI", f"{total_investment:.2f} PLN")