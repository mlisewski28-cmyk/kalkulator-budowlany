import json
import time
import os
import re
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit

# =============================================================================
# KONFIGURACJA KATEGORII DO POBRANIA
# Podaj tutaj nazwę kategorii i przypisany do niej link ze sklepu.
# =============================================================================
CATEGORIES_TO_SCRAPE = {
    "Farby Ogólnego Stosowania": "https://mrowkaonline.com/kategoria-produkty/farby/farby-farby/farby-ogolnego-stosowania/?filter_tax_product_cat=7714",
    "Farby (Inne)": "https://mrowkaonline.com/kategoria-produkty/farby/?filter_tax_product_cat=7515",
    "Chemia Budowlana (7471)": "https://mrowkaonline.com/sklep/?filter_tax_product_cat=7471",
    "Materiały Budowlane (7566)": "https://mrowkaonline.com/sklep/?filter_tax_product_cat=7566",
    "Narzędzia (7838)": "https://mrowkaonline.com/sklep/?filter_tax_product_cat=7838",
    "Ogród (7441)": "https://mrowkaonline.com/sklep/?filter_tax_product_cat=7441",
    "Oświetlenie (7551)": "https://mrowkaonline.com/sklep/?filter_tax_product_cat=7551"
    # Dodaj kolejne według wzoru:
    # "Twoja Nazwa Kategorii": "Adres URL",
}

OUTPUT_FILENAME = "produkty.json"


def build_page_url(base_url: str, page_num: int) -> str:
    """Tworzy adres URL dla konkretnej podstrony (np. /page/2/?filter=...)."""
    if page_num == 1:
        return base_url

    split_url = urlsplit(base_url)
    
    # Sklep mrowkaonline.com obsługuje paginację z parametrami poprzez wstawienie /page/N/
    # Musimy to obsłużyć inaczej w zależności, czy link ma ścieżkę (np. /kategoria/...) czy to główny /sklep/
    path = split_url.path.rstrip('/')
    if path == "/sklep":
        path = f"/sklep/page/{page_num}/"
    elif path.startswith("/kategoria-produkty"):
        path = f"{path}/page/{page_num}/"
    else:
        # Awaryjnie, doczepiamy po prostu /page/N/
        path = f"{path}/page/{page_num}/"

    return urlunsplit((split_url.scheme, split_url.netloc, path, split_url.query, split_url.fragment))


def get_scraper():
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )


def extract_products_from_page(scraper, url: str) -> list[dict]:
    """Pobiera i wyciąga towary z pojedynczej strony."""
    products = []
    try:
        response = scraper.get(url, timeout=15)
        if response.status_code != 200:
            return products

        soup = BeautifulSoup(response.text, 'html.parser')

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(url, href)

            # Skanujemy tylko linki do kart produktów
            if '/produkt/' in full_url:
                title = a_tag.get_text(strip=True) or a_tag.get('title', '')
                clean_title = ' '.join(title.split())

                if clean_title and len(clean_title) > 3:
                    if not any(p['url'] == full_url for p in products):
                        products.append({
                            "name": clean_title,
                            "url": full_url
                        })
    except Exception as e:
        print(f"⚠️ Błąd pobierania {url}: {e}")

    return products


def scrape_category_with_pagination(category_name: str, start_url: str, max_pages: int = 50) -> dict:
    """Skanuje kategorię przechodząc strona po stronie."""
    scraper = get_scraper()
    category_products = {}
    page = 1

    print(f"\n🚀 Rozpoczynam pobieranie kategorii: '{category_name}'")

    while page <= max_pages:
        page_url = build_page_url(start_url, page)
        print(f"  📄 Skanowanie strony {page}: {page_url}")

        page_products = extract_products_from_page(scraper, page_url)

        if not page_products:
            print(f"  🏁 Brak produktów na stronie {page}. Koniec podstron.")
            break

        new_count = 0
        for prod in page_products:
            if prod["name"] not in category_products:
                category_products[prod["name"]] = prod["url"]
                new_count += 1

        print(f"     ✅ Pobrano {len(page_products)} produktów na tej stronie ({new_count} nowych).")

        if new_count == 0 and page > 1:
            print("  🏁 Brak nowych unikalnych produktów. Koniec podstron.")
            break

        page += 1
        time.sleep(1.5)

    return category_products


def run_crawler():
    catalog = {}
    # Odczytujemy stary plik, żeby nie kasować poprzednich danych, jeśli je mamy
    if os.path.exists(OUTPUT_FILENAME):
        try:
            with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
        except Exception:
            catalog = {}

    for cat_name, url in CATEGORIES_TO_SCRAPE.items():
        products = scrape_category_with_pagination(cat_name, url)
        if products:
            catalog[cat_name] = products

    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=4)

    print(f"\n🎉 Sukces! Zapisano wszystkie dane w pliku '{OUTPUT_FILENAME}'.")


if __name__ == "__main__":
    run_crawler()