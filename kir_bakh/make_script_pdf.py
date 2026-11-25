import os
import tempfile
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Register DejaVu Cyrillic fonts
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DVSerif", os.path.join(FONT_DIR, "DejaVuSerif.ttf")))
pdfmetrics.registerFont(TTFont("DVSerif-B", os.path.join(FONT_DIR, "DejaVuSerif-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DVSans", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DVSans-B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))

PAPER_BG = colors.HexColor("#F7F3EA")
CARD_BG = colors.HexColor("#EFE8D8")
NARR_BG = colors.HexColor("#FBF8F2")
BORDER = colors.HexColor("#CBBCA3")
INK = colors.HexColor("#2B221B")
ACCENT = colors.HexColor("#734E2D")
MUTED = colors.HexColor("#6A5846")

OUT_PDF = "kir_bakh/scenariy_priklyucheniya_kir_bakha_tort.pdf"


def prep_img(src_path: str, tmp_dir: str, max_w_px=1000) -> tuple[str, float, float]:
    im = PILImage.open(src_path).convert("RGB")
    w, h = im.size
    if w > max_w_px:
        nh = int(h * max_w_px / w)
        im = im.resize((max_w_px, nh), PILImage.Resampling.LANCZOS)
    out = os.path.join(tmp_dir, os.path.basename(src_path) + ".jpg")
    im.save(out, "JPEG", quality=88, optimize=True)
    return out, im.size[0], im.size[1]


def draw_page_chrome(canvas, doc):
    canvas.saveState()
    pw, ph = A4
    # Warm paper background
    canvas.setFillColor(PAPER_BG)
    canvas.rect(0, 0, pw, ph, stroke=0, fill=1)
    # Subtle outer frame
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(1.0)
    canvas.roundRect(11 * mm, 11 * mm, pw - 22 * mm, ph - 22 * mm, 5 * mm, stroke=1, fill=0)
    # Footer
    canvas.setFont("DVSans", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 13.5 * mm, "Приключения Кир Баха и Петьки — Серия 1: «Торт на 18-летие»")
    canvas.drawRightString(pw - 18 * mm, 13.5 * mm, f"Стр. {doc.page}")
    canvas.restoreState()


def build_pdf():
    tmp_dir = tempfile.mkdtemp(prefix="kb_pdf_")
    doc = SimpleDocTemplate(
        OUT_PDF,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Приключения Кир Баха и Петьки — Серия 1: Торт на 18-летие",
        author="Приключения Кир Баха",
    )

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle(
        "Title",
        fontName="DVSerif-B",
        fontSize=21,
        leading=26,
        textColor=INK,
        alignment=1,
        spaceAfter=4,
    )
    s_sub = ParagraphStyle(
        "Sub",
        fontName="DVSerif-B",
        fontSize=14,
        leading=19,
        textColor=ACCENT,
        alignment=1,
        spaceAfter=6,
    )
    s_meta = ParagraphStyle(
        "Meta",
        fontName="DVSans",
        fontSize=9.5,
        leading=13,
        textColor=MUTED,
        alignment=1,
        spaceAfter=10,
    )
    s_h2 = ParagraphStyle(
        "H2",
        fontName="DVSerif-B",
        fontSize=13.5,
        leading=18,
        textColor=ACCENT,
        spaceBefore=8,
        spaceAfter=5,
    )
    s_body = ParagraphStyle(
        "Body",
        fontName="DVSans",
        fontSize=10,
        leading=14.2,
        textColor=INK,
        spaceAfter=4,
    )
    s_label = ParagraphStyle(
        "Label",
        fontName="DVSans-B",
        fontSize=9.5,
        leading=13.5,
        textColor=ACCENT,
        spaceBefore=4,
        spaceAfter=2,
    )
    s_narr = ParagraphStyle(
        "Narr",
        fontName="DVSerif",
        fontSize=10,
        leading=14.5,
        textColor=INK,
    )
    s_dial = ParagraphStyle(
        "Dial",
        fontName="DVSans",
        fontSize=9.8,
        leading=13.8,
        textColor=INK,
        leftIndent=8,
        spaceAfter=2.5,
    )

    content_w = A4[0] - 36 * mm
    story = []

    # Header
    story.append(Paragraph("«Приключения Кир Баха и Петьки»", s_title))
    story.append(Paragraph("Серия 1: «Торт на 18-летие»", s_sub))
    story.append(
        Paragraph(
            "Сценарий и иллюстрированная раскадровка · Стиль: советская книжная графика · Хронометраж ролика: 1 мин 53 сек",
            s_meta,
        )
    )

    # Cover duo image
    duo_jpg, dw, dh = prep_img("kir_bakh/kir_and_petka_duo.png", tmp_dir)
    img_w = content_w * 0.86
    img_h = img_w * (dh / dw)
    duo_im = Image(duo_jpg, width=img_w, height=img_h)
    duo_im.hAlign = "CENTER"
    story.append(duo_im)
    story.append(Spacer(1, 8))

    # Characters
    story.append(Paragraph("Персонажи", s_h2))
    chars = [
        ("Кир Бах (7 лет)", "шустрый, веснушчатый непоседа в твидовой кепке, голубой рубашке с подтяжками и подвёрнутых штанах. В руках или за поясом — деревянная дудочка. Сначала делает, потом смотрит, что получилось."),
        ("Петька (14 лет)", "высокий, долговязый, рассудительный старший брат в полосатом свитере и сине-сером комбинезоне. Носит с собой старый медный фонарь («на всякий случай») и зелёное яблоко («перекусить по дороге»)."),
        ("Друг (14 лет)", "добродушный, чуть пухловатый кудрявый рыжеватый паренёк с веснушками в кухонном фартуке. Хранитель большой кухни, венчика и толстой поваренной книги."),
        ("Старшая сестра (18 лет)", "обаятельная именинница с волнистыми каштановыми волосами, в скромном оливково-зелёном платье с белым воротничком. Ждёт гостей и братьев к праздничному чаю."),
        ("Полосатый кот", "невозмутимый уличный хулиган, ставший причиной катастрофы с первым тортом."),
    ]
    for name, desc in chars:
        story.append(Paragraph(f'<font name="DVSans-B">{name}</font> — {desc}', s_body))

    story.append(Spacer(1, 4))
    story.append(
        KeepTogether([
            Paragraph("Заставка (0:00 – 0:03)", s_h2),
            Paragraph(
                '<font name="DVSans-B">Изображение:</font> на тёплой шероховатой бумаге появляется виньетка с идущими рядом Петькой и Киром и заголовок серии.',
                s_body,
            ),
            Paragraph(
                '<font name="DVSans-B">Звук:</font> лёгкая задорная мелодия деревянной флейты и переливы челесты.',
                s_body,
            ),
        ])
    )

    scenes = [
        {
            "title": "Сцена 1. Беда по дороге",
            "img": "kir_bakh/cake_story/01_dropped_cake.png",
            "visual": "Тихая мощёная улочка у кондитерской. Петька и Кир замерли в комическом ужасе. На брусчатке лежит раскрытая картонная коробка, из которой розовой и белой лужей вытек расплющенный торт. Рядом невозмутимо сидит полосатый кот и с довольным видом слизывает крем с носа.",
            "narr": "«В тот самый день, когда старшей сестре исполнилось восемнадцать лет, Петька и семилетний Кир отправились за праздничным тортом. Дорога была короткой, но уличный кот под ногами решил всё иначе. Торт плюхнулся прямо на мостовую! Что же теперь делать братьям?»",
            "dial": [
                ("Кир (прикрыв рот ладошкой):", "Ой... Петь, а если мы его обратно в коробку сложим?"),
                ("Петька (хватаясь за голову):", "Куда сложим?! Там кот уже полрозы съел! И денег больше нет, а через час гости придут!"),
                ("Кир (хитро щурясь):", "Значит, пойдём к нашему другу на кухню — сами испечём!"),
            ],
            "sound": "Шутливый марш пиццикато; глухой «плюх» коробки; довольное мурлыкающее «мяу» кота.",
        },
        {
            "title": "Сцена 2. Поваренная книга и мука",
            "img": "kir_bakh/cake_story/02_friend_kitchen_cookbook.png",
            "visual": "Уютная, заставленная банками и кастрюлями кухня друга. На плите пыхтит самовар и чайник, за окном кружится лёгкий снежок. Слева Петька с озадаченным видом чешет затылок над раскрытой толстой книгой с надписью «РЕЦЕПТЫ». В центре маленький Кир в большом фартуке взобрался на табурет и радостно вытряхивает в миску целый мешок «МУКА». Справа друг в клетчатой рубашке и фартуке с недоверием крутит ручной венчик.",
            "narr": "«Возвращаться с пустыми руками нельзя! Братья помчались на кухню к своему другу и достали толстую поваренную книгу. Петька принялся читать рецепт вслух, а Кир влез на табурет и высыпал целый мешок муки прямо на глаз!»",
            "dial": [
                ("Петька (водя пальцем по странице):", "Так... «Взять триста граммов просеянной муки, щепотку соды и...» Кир, стой! Написано — триста граммов!"),
                ("Кир (весело):", "А я на глаз! У нас же старшая сестра, ей восемнадцать — значит, торт должен быть большой!"),
                ("Друг (подозрительно глядя на миску):", "Ребята, у меня плохое предчувствие..."),
            ],
            "sound": "Шелест страниц старой книги; гулкое «пуф!» облака муки; поскрипывание ручного венчика.",
        },
        {
            "title": "Сцена 3. Переполох на кухне",
            "img": "kir_bakh/cake_story/03_kitchen_disaster.png",
            "visual": "Полный кухонный хаос, все трое перемазаны мукой. Слева из приоткрытой духовки валит густой чёрный дым — озабоченный Петька склонился и светит прямо в дым своим медным фонарём. Посреди стола огромное дрожжевое тесто переливается через край миски белым вулканом. Кир в ужасе смотрит на гору теста. Справа друг в панике подпрыгнул на месте, ловя в воздухе разбившиеся яичные скорлупки и вылетевшую ложку.",
            "narr": "«Но по книге ничего не выходило! Тесто полезло из миски пенным вулканом, в духовке всё задымилось, а скорлупки от яиц разлетелись по всей кухне. Петька светил фонарём в дым, Кир ахнул, а друг еле успевал ловить ложки!»",
            "dial": [
                ("Петька (кашляя, светит фонарём):", "Ничего не видно! Тут, кажется, наш первый корж в уголь превратился!"),
                ("Кир:", "Петька, оно живое!! Оно сейчас весь стол съест!"),
                ("Друг (ловя ложку на лету):", "Спасайте яйца! Убирайте книгу, от неё одни неприятности!"),
            ],
            "sound": "Быстрая комическая музыкальная погоня, бульканье теста, звон ложек, мультяшный «боинг».",
        },
        {
            "title": "Сцена 4. Дружная вторая попытка",
            "img": "kir_bakh/cake_story/04_teamwork_breakthrough.png",
            "visual": "Кухня прибрана, поваренная книга отложена далеко в сторону на край стола. Все трое работают спокойно и слаженно. Петька серьёзно и аккуратно нарезает тонкими дольками своё зелёное яблоко для начинки. По центру уже стоят два ровных румяных коржа со слоем белого крема; Кир на табурете бережно выкладывает сверху малину и чернику. Друг с тёплой улыбкой взбивает в миске нежный крем.",
            "narr": "«Тогда ребята отряхнулись от муки и решили готовить дружно, без мудрёных инструкций. Петька аккуратно нарезал своё зелёное яблоко, друг замесил нежный крем, а Кир старательно украсил коржи свежими ягодами.»",
            "dial": [
                ("Петька (сосредоточенно):", "Яблоко кисленькое — самое то между коржами положить."),
                ("Кир (старательно раскладывая ягоды):", "А ягодки — по кругу, как бусы!"),
                ("Друг:", "Вот теперь похоже на настоящий торт. Без всяких мудрёных книжек!"),
            ],
            "sound": "Спокойная тёплая мелодия в ритме вальса; лёгкий стук ножа по доске при нарезке яблока.",
        },
        {
            "title": "Сцена 5. Старшая сестра в ожидании",
            "img": "kir_bakh/cake_story/05_sister_18_waiting.png",
            "visual": "Уютная светлая гостиная с обоями в цветочек, книжным шкафом, старым радиоприёмником и дремлющим на кресле котом. На столе с вышитой скатертью стоят чайные чашки, заварочный чайник, вазочка с ромашками и совершенно пустая белая подставка под торт. Возле стола стоит 18-летняя сестра в оливковом платье с белым воротничком и нежно, но слегка встревоженно поглядывает на наручные часы.",
            "narr": "«Тем временем старшая сестра уже накрыла праздничный стол к чаю. Она то и дело поглядывала на часы и тихонько волновалась: куда же запропастились её младшие братья?»",
            "dial": [
                ("Сестра (глядя на часы и улыбаясь с лёгкой тревогой):", "Половина пятого... Ну где же Петька с Киром? Лишь бы в какую-нибудь историю не влипли."),
            ],
            "sound": "Лиричная тихая музыка; деликатное, чуть тревожное «тик-так» наручных часов.",
        },
        {
            "title": "Сцена 6. Всё получилось!",
            "img": "kir_bakh/cake_story/06_happy_finale.png",
            "visual": "Та же гостиная. В комнату вошли Петька, друг и Кир. У Петьки и друга на щеках остались милые белые пятнышки муки, Кир снял кепку и с сияющей улыбкой держит наготове свою деревянную дудочку. Петька и друг вдвоём торжественно несут пышный домашний торт, украшенный дольками яблока, ягодами и горящими свечами. 18-летняя сестра прижимает ладони к груди и звонко смеётся от счастья.",
            "narr": "«И вот дверь распахнулась! Вся компания, ещё чуть в муке, внесла пышный домашний торт со свечами и яблоками, а Кир приготовил свою дудочку для праздничного туша. Сестра рассмеялась от счастья, ведь такой торт оказался в сто раз вкуснее любого магазинного!»",
            "dial": [
                ("Петька (слегка смущённо):", "С восемнадцатилетием! Мы, правда, чуть-чуть задержались..."),
                ("Кир (поднимая дудочку):", "Зато сами пекли! Сейчас я сыграю праздничный туш!"),
                ("Сестра (хохоча от радости):", "Ой, мальчишки, да у вас вся щёчка в муке! Это самый лучший торт в моей жизни!"),
            ],
            "sound": "Яркая весёлая фанфара деревянной дудочки Кира, звонкий праздничный аккорд челесты, финальный тёплый марш.",
        },
    ]

    for sc in scenes:
        block = []
        block.append(Paragraph(sc["title"], s_h2))

        jpg, w, h = prep_img(sc["img"], tmp_dir)
        iw = content_w * 0.88
        ih = iw * (h / w)
        im = Image(jpg, width=iw, height=ih)
        im.hAlign = "CENTER"
        block.append(im)
        block.append(Spacer(1, 5))

        block.append(Paragraph(f'<font name="DVSans-B" color="#734E2D">Визуальное действие:</font> {sc["visual"]}', s_body))

        # Narrator box
        narr_tbl = Table(
            [[Paragraph(f'<font name="DVSans-B" color="#734E2D">Диктор (закадровый текст):</font><br/>{sc["narr"]}', s_narr)]],
            colWidths=[content_w],
        )
        narr_tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), NARR_BG),
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        block.append(Spacer(1, 3))
        block.append(narr_tbl)
        block.append(Spacer(1, 4))

        block.append(Paragraph("Реплики героев:", s_label))
        for who, line in sc["dial"]:
            block.append(Paragraph(f'<font name="DVSans-B">{who}</font> {line}', s_dial))

        block.append(Paragraph(f'<font name="DVSans-B" color="#734E2D">Звук:</font> {sc["sound"]}', s_body))
        block.append(Spacer(1, 6))

        story.append(KeepTogether(block))

    # Finale caption
    fin_tbl = Table(
        [[Paragraph(
            '<font name="DVSerif-B" size="11.5">Финальный титр (1:50 – 1:53):</font><br/>'
            '«Вот так и бывает! Домашний торт с душой всегда вкуснее магазинного. Конец.»',
            s_narr
        )]],
        colWidths=[content_w],
    )
    fin_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
            ("BOX", (0, 0), (-1, -1), 1.0, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(KeepTogether([Spacer(1, 4), fin_tbl]))

    doc.build(story, onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
    print(f"Built {OUT_PDF}")


if __name__ == "__main__":
    build_pdf()
