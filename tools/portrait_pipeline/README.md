# Portrait / Focus-icon Pipeline

Инструменты для полу-автоматической подготовки артов (портреты лидеров, иконки
фокусов, идей, советников) в формат, который ест HOI4. Базовый путь работает на
Python 3 + Pillow, а для совместимого с игрой финального DDS можно использовать
встроенный в репозиторий `texconv.exe`.

Два скрипта:

| Скрипт | Что делает |
|--------|-----------|
| `scrape.py`  | качает арт по имени персонажа с **warcraft.wiki.gg** (MediaWiki API) |
| `convert.py` | режет/масштабирует PNG/JPG в готовый `.dds` нужного размера |
| `batch_icons.py` | режет контактный лист по слотам в любой UI-пресет (`focus`, `idea`, `advisor`, `leader`) |
| `batch_ideas.py` | режет контактный лист по слотам и сразу выпускает пачку `.dds` идей |

Генерация нейросетью в сам пайплайн не встроена, но пайплайн под неё уже
заточен: можно генерить PNG в любом внешнем чатботе, а потом прогонять через
`convert.py` / `batch_icons.py` до итогового игрового формата.

---

## Целевые форматы HOI4 (замерено по этому моду)

| Пресет    | Размер     | Куда кладём                     | Пример из мода |
|-----------|-----------|----------------------------------|----------------|
| `focus`   | 140 × 140 | `gfx/interface/focus_tree/`      | custom focus icon |
| `leader`  | 156 × 210 | `gfx/leaders/<TAG>/`             | `Aiden_Perenolde.dds` |
| `idea`    | 64 × 64   | `gfx/interface/ideas/`           | `alliance_idea.dds` |
| `advisor` | 65 × 67   | `gfx/interface/advisors/`        | `advisor_generic.dds` |

Формат файла: `.dds`. Для HOI4-иконок в этом проекте сейчас практический рабочий
вариант такой:

- `DXT1` + `1 mip level` через `texconv` — основной путь для фокусов, где нужна
  жёсткая прозрачность без полутонов;
- `DXT5` (BC3) остаётся запасным вариантом, если нужна мягкая альфа.

> **Мипмапы:** Pillow пишет DDS без мип-уровней. Для UI-спрайтов HOI4 это
> нормально — интерфейс не масштабирует их в даль. Если когда-нибудь понадобятся
> «эталонные» мипмапы (для 3D/карты) — см. раздел *Опционально: texconv* ниже.

---

## Быстрый старт (полный цикл)

```bash
cd tools/portrait_pipeline

# 1. Скачать арты по именам
python scrape.py "Aiden Perenolde" "Genn Greymane" --out raw/

# 2. Порезать в портреты лидеров 156x210 -> .dds
python convert.py leader raw/ --out out/

# 3. Проверить глазами out/*.dds, переименовать под имя спрайта,
#    скопировать в живую папку мода:
#    C:\Games\Hearts of Azeroth VinerX Editon\gfx\leaders\ALT\
```

---

## scrape.py — скрап артов из интернета

Тянет **главную (инфобокс) картинку** страницы персонажа в оригинальном
разрешении через официальный MediaWiki API вики. Никакого парсинга HTML —
стабильно и легально для личного мод-использования.

```bash
# по именам (сколько угодно)
python scrape.py "Anduin Wrynn" "Jaina Proudmoore" --out raw/

# из файла-списка (одно имя на строку, # — комментарий)
python scrape.py --file names.txt --out raw/

# ВСЕ картинки со страницы (альт-позы, фан-арт) — потом выбрать руками
python scrape.py "Genn Greymane" --all --out raw/
```

Флаги: `--out DIR` (куда), `--all` (все изображения, а не только лид),
`--delay СЕК` (пауза между страницами, по умолчанию 1с — не долбим вики).

Имя не обязано быть точным — скрипт сам ищет ближайшую страницу через поиск.
Источник по умолчанию — `warcraft.wiki.gg` (актуальная вики WoW). Сменить домен
можно в константе `API` вверху файла.

---

## convert.py — нарезка в .dds

```bash
python convert.py <preset> <input> [опции]
```

`<preset>`: `focus` | `leader` | `idea` | `advisor` | `custom`
`<input>`: файл, папка или glob (`"raw/*.png"`).

Опции:

| Флаг | Смысл |
|------|-------|
| `--out DIR`      | папка вывода (по умолчанию `out/`) |
| `--fit cover`    | (по умолч.) масштаб «в заполнение» + центр-кроп. Для портретов |
| `--fit contain`  | масштаб «влезть целиком» + прозрачные поля. Для лого/иконок |
| `--focus-top`    | при `cover` смещает кроп к голове (якорь 0.25) — чтобы у портрета не срезало макушку |
| `--anchor V`     | тонкая настройка вертикали кропа: `top`\|`center`\|`bottom` или число `0.0-1.0` |
| `--format DXT5`  | (по умолч.) с альфой. `DXT1` — меньше, но альфа 1-бит |
| `--size 120x120` | только с пресетом `custom` |
| `--suffix _land` | добавить к имени файла на выходе |

Примеры:

```bash
python convert.py focus  "raw/*.png" --out out/focus  --fit contain
python convert.py leader raw/        --out out/leaders --focus-top
python convert.py custom art.png     --out out --size 200x260
```

### Генерация вне пайплайна -> нарезка внутри пайплайна

Рабочая схема для постановки на поток:

1. Генерируешь PNG в любом внешнем чатботе / генераторе.
2. Просишь сразу делать либо одиночную иконку, либо контактный лист `2x3`,
   `3x3`, `4x2` с жёстко зафиксированным порядком слотов.
3. Фон делаешь хромакейным, чтобы потом не вырезать вручную:
   `#00FFF0` или другой цвет, который гарантированно не встречается в арте.
4. Дальше даже агент без распознавания картинки может просто взять готовый PNG,
   манифест слотов и прогнать `batch_icons.py` / `convert.py`.

Ключевая мысль: агенту не нужно “понимать” изображение, если генератор уже
выдал лист в правильной сетке и с правильным фоном.

### Шаблоны промтов для внешнего чатбота

Ниже шаблоны не под конкретную модель, а под задачу. Их можно копировать почти
как есть и менять только тему, предмет и список позиций.

#### 1. Одиночная иконка фокуса

Использовать, когда нужна одна заметная иконка под фокус.

```text
Create a single fantasy strategy-game focus icon.
Subject: [КРАТКОЕ ОПИСАНИЕ].
Composition: one main centered object, large readable silhouette, no tiny edge details.
Background: solid chroma key background #00FFF0, perfectly flat and uniform.
Style: polished Warcraft-inspired fantasy prop art, high contrast, readable at small size.
Constraints: no frame, no border, no text, no UI elements, no cropped object, keep clear padding around the object, no cyan reflections or cyan glow on the object.
Output: square image, high resolution.
```

#### 2. Одиночная иконка идеи / нацдуха

Использовать, когда нужен символ, который потом ужмётся до `64x64`.

```text
Create a single fantasy national spirit icon for a strategy game.
Subject: [КРАТКОЕ ОПИСАНИЕ].
Composition: one dominant centered symbol only, simple silhouette, minimal clutter, large empty margins around the object.
Background: solid chroma key background #00FFF0, perfectly uniform.
Style: high-contrast fantasy icon art, readable at 64x64, no scene, no secondary objects.
Constraints: no frame, no border, no text, no cropped edges, no cyan spill, no fog overlapping the silhouette.
Output: square image, high resolution.
```

#### 3. Дух / магический шар / лоа

Это частный шаблон под духи, где важна сферическая композиция.

```text
Create a fantasy spirit icon for a strategy game.
Subject: [НАЗВАНИЕ ДУХА ИЛИ СУЩНОСТИ].
Composition: spherical composition, glowing orb or circular magical core, centered face / mask / spirit essence inside the sphere, strong readable silhouette.
Background: solid chroma key background #00FFF0, perfectly flat.
Style: Warcraft-inspired mystical artifact icon, high contrast, readable at small size.
Constraints: no frame, no text, no cropped edges, keep generous empty padding around the sphere, no cyan glow on the subject.
Output: square image, high resolution.
```

#### 4. Контактный лист под пакетную нарезку

Использовать, когда хочешь сразу пачку иконок.

```text
Create a [ROWS]x[COLS] contact sheet of separate fantasy strategy-game icons.
Each cell must contain exactly one centered icon on a solid chroma key background #00FFF0.
All cells must have identical size and spacing, arranged in a strict grid.
Do not merge icons across cells. Keep padding inside each cell so the object does not touch the edges.
No frame, no text, no labels, no UI.
Style: polished Warcraft-inspired fantasy icon art, high contrast, readable at small size.
Slot order, left to right and top to bottom:
1. [IDEA / FOCUS 1]
2. [IDEA / FOCUS 2]
3. [IDEA / FOCUS 3]
4. [IDEA / FOCUS 4]
5. [IDEA / FOCUS 5]
6. [IDEA / FOCUS 6]
```

Если нужен лист для фокусов, полезно прямо дописывать:

```text
Each icon should fit comfortably inside a square crop and remain readable after reduction to a small in-game focus icon.
```

### Что обязательно говорить генератору

Это важнее стилистики. Если это не проговорить, потом начинаются проблемы на
краях и при прозрачности.

- `solid chroma key background #00FFF0`
- `no frame, no border, no text`
- `one object per cell`
- `keep padding around the object`
- `do not touch edges`
- `no cyan spill / no cyan glow / no cyan reflections`
- `readable at small size`
- `strict grid layout` для контактных листов

### Handoff-пакет для агента без распознавания

Чтобы другой агент мог дорезать лист до игры вообще без визуального анализа,
ему достаточно передать вот такой пакет данных:

```text
1. Путь к PNG:
   C:\art\gnome_focus_sheet_01.png

2. Что это:
   focus icons

3. Сетка:
   2 rows, 3 cols

4. Цвет фона:
   #00FFF0

5. Порядок слотов:
   1 = mechanical_defenses
   2 = gnomish_ingenuity
   3 = flying_machines
   4 = gyrocopter_squadrons
   5 = spider_tank_development
   6 = mechanical_warfare

6. Финальный формат:
   DDS via texconv, DXT1, 1 mip level
```

После этого агент может механически выполнить пайплайн.

Пример для фокусов:

```bash
python batch_icons.py manifest.json --out out/focus ^
  --preset focus ^
  --safe-pad 10 ^
  --chroma-key "#00FFF0" ^
  --chroma-threshold 36 ^
  --chroma-softness 10 ^
  --despill 0.25 ^
  --texconv ^
  --texconv-format DXT1 ^
  --mip-levels 1
```

Пример для идей:

```bash
python batch_icons.py manifest.json --out out/ideas ^
  --preset idea ^
  --icon-safe ^
  --chroma-key "#00FFF0" ^
  --chroma-threshold 36 ^
  --chroma-softness 10 ^
  --despill 0.25 ^
  --texconv ^
  --texconv-format DXT1 ^
  --mip-levels 1
```

### Текущая рабочая спецификация по проекту

Ниже зафиксированы практические размеры, которые мы используем в этом проекте
для нового пайплайна арта:

| Тип | Размер | Примечание |
|-----|--------|------------|
| Focus icon | `140x140` | базовый целевой размер для новых иконок фокусов |
| National spirit / advisor-style icon | `64x64` / `65x67` | идеи и советники идут отдельными пресетами |
| Leader portrait | `156x210` | портреты лидеров |

Дополнительно:

- итоговый формат: `.dds`;
- для новых фокусов и иконок, где тестируем жёсткую прозрачность, основной
  экспортный путь сейчас: `texconv` -> `DXT1` -> `1 mip level`;
- для фокусов сетка дерева по скрипту остаётся отдельной темой:
  `x +1 = 96 px`, `y +1 = 130 px`;
- `PPI` для самой игры не является ключевым параметром загрузки DDS, но
  исходники имеет смысл держать детальными и без артефактов до финальной конвертации.

### Рекомендуемый процесс для иконок идей (`64x64`)

Проблема большинства AI-картинок для HOI4-идей одна и та же: генератор рисует
слишком много деталей у самой кромки, а после уменьшения до `64x64` предметы
липнут к рамке или визуально обрезаются.

Для идей теперь есть безопасный режим:

```bash
python convert.py idea raw/my_icon.png --out out/ideas --icon-safe --preview-png
```

Что делает `--icon-safe`:

- принудительно использует `--fit contain` вместо `cover`;
- оставляет внутренние прозрачные поля (safe padding) по краям;
- помогает удержать главный силуэт внутри безопасной зоны.

`--preview-png` сохраняет рядом обычный `.png`, чтобы быстро глазами проверить
итоговый вид `64x64` до копирования в мод.

Практические правила для генерации исходника:

- один главный объект, а не сцена из 4-5 предметов;
- без нарисованной рамки, без касаний с краями;
- тёмный простой фон, высокий контраст;
- важный силуэт по центру;
- для духов/лоа предпочтительна сферическая композиция: шар, маска в ореоле,
  тотемное лицо в круглом свечении.

Хороший шаблон промпта:

```text
single centered fantasy icon, no border, no frame, no cropped elements,
large readable silhouette, simple dark background, readable at 64x64,
high contrast, minimal clutter
```

### Пакетный режим: список позиций -> пачка иконок

Если генеришь не по одной иконке, а листами `2x3`, `3x3` и т.д., удобнее не
резать руками, а описывать позиции в JSON-манифесте.

Сначала создай шаблон:

```bash
python batch_ideas.py --write-template batch_manifest.json
```

Потом заполни:

- `sheet` - путь к сгенерированному листу;
- `grid.rows` / `grid.cols` - сетка листа;
- `prefix` - общий префикс имён;
- `items[].slot` - позиция на листе;
- `items[].name` - итоговое имя файла без `.dds`.

Пример:

```json
{
  "sheet": "C:/art/amani_sheet_01.png",
  "grid": { "rows": 2, "cols": 3 },
  "safe_pad": 8,
  "prefix": "AMA_",
  "items": [
    { "slot": 1, "name": "sw_loa_blessings_idea" },
    { "slot": 2, "name": "sw_spirit_guardians_idea" },
    { "slot": 3, "name": "sw_rangers_nightmare_idea" },
    { "slot": 4, "name": "sw_hex_warfare_idea" },
    { "slot": 5, "name": "sw_blessed_axes_idea" },
    { "slot": 6, "name": "sw_eternal_hatred_idea" }
  ]
}
```

Запуск:

```bash
python batch_ideas.py batch_manifest.json --out out/amani_ideas
```

На выходе для каждой позиции будут:

- итоговый `64x64` `.dds`;
- PNG-превью того же итогового размера;
- временный кроп ячейки в `_tmp_crops/`.

Слоты можно задавать:

- числом `1..N` (слева направо, сверху вниз);
- строкой `"row,col"`;
- массивом `[row, col]`.

> `--focus-top` работает, когда исходник **выше** рамки 156×210 (вертикальный
> портрет) — тогда кроп не срезает голову. Если исходник **широкий**
> (горизонтальный), вертикального излишка нет и флаг ничего не меняет — такой
> арт лучше руками кропнуть до вертикали или взять `--fit contain`.

## Просмотр .dds

`.dds` штатный проводник не открывает. Быстрый способ глянуть результат —
декодировать обратно в PNG:

```bash
python -c "from PIL import Image; Image.open('out/x.dds').convert('RGBA').save('x.png')"
```

(У тебя также есть собственный предпросмотрщик `.dds` — можно смотреть им напрямую.)

---

## Важные оговорки

- **Имена файлов.** Спрайты HOI4 не любят пробелы/запятые/кириллицу в имени
  файла. `scrape.py` сохраняет как на вики (`Genn,_Cursed_King_HS.png`) — перед
  копированием в мод переименуй `.dds` под то, на что ссылается `.gfx`
  (напр. `GEN_greymane.dds`), иначе игра не найдёт текстуру.
- **Привязка к `.gfx`.** Скрипты только делают файлы; строку
  `spriteType = { name = "GFX_..." texturefile = "gfx/..." }` пока прописываешь
  вручную (в `interface/hoa_focus.gfx` и т.д.). Автогенерацию этих записей можно
  добавить отдельным шагом, если попросишь.
- **Живая папка vs dev.** Бинарники (`gfx/`) лежат только в играбельной папке
  `C:\Games\Hearts of Azeroth VinerX Editon`, в dev-worktree `C:\Games\HOA-dev`
  их нет (разреженная копия). Готовые `.dds` копируй в живую папку, а игру —
  полностью перезапускай, чтобы текстуры перечитались.
- **Права.** Скачанный арт принадлежит Blizzard и художникам. Это только для
  личного некоммерческого мода.

---

## Опционально: texconv (эталонные DDS с мипмапами)

Если понадобится «идеальный» DDS как у ванилы (мипмапы, точный BC3):
скачать `texconv.exe` из [Microsoft DirectXTex](https://github.com/microsoft/DirectXTex/releases),
положить рядом, и после `convert.py` прогнать:

```bash
texconv -f BC3_UNORM -m 0 -y -o out_dds out/*.dds
```

Для UI-спрайтов это НЕ обязательно — базовый Pillow-путь игра принимает.
