from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "test_web"

templates = Jinja2Templates(directory=str(WEB_DIR))

app.mount(
    "/static",
    StaticFiles(directory=str(WEB_DIR / "static")),
    name="static")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.get("/contact")
def contact(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={}
    )

@app.get("/checkout")
def checkout(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={}
    )

@app.get("/cart")
def cart(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={}
    )

@app.get("/account")
def order(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={}
    )

@app.get("/products")
def products(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="products.html",
        context={}
    )