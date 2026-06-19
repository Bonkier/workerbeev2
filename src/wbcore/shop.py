from .utils.utils import *
from itertools import combinations_with_replacement
from .utils import params as p
from .teams import TEAMS
from .cache import CACHE

loc_shop = loc_rgb(conf=0.83, wait=False, method=cv2.TM_SQDIFF_NORMED)
shop_click = loc_shop(click=True, wait=5)

item_points = {1: 3, 2: 6, 3: 10, 4: 15}
COMBOS = list(combinations_with_replacement(range(1, 5), 3))
get_tier3 = [((1, 1, 4), 21), ((1, 2, 3), 19), ((1, 2, 4), 24), ((1, 3, 3), 23), ((2, 2, 2), 18), ((2, 2, 3), 22)]

EXTRA = []
for i in range(3, 6):
    EXTRA += list(combinations_with_replacement(range(1, 5), i))

TWO_ITEM_COMBOS = list(combinations_with_replacement(range(1, 5), 2))


enhance_cost = {
    1: 150,
    2: 180,
    3: 225,
    4: 300,
}

fusion_ranges = {
    1: (9, 10),
    2: (11, 16),
    3: (17, 24),
    4: (25, 45)
}

super_ranges = {
    1: (9, 9),
    2: (10, 14),
    3: (15, 21),
    4: (22, 75)
}


def combo_counter(combo):
    counter = {}
    for tier in combo:
        if tier in counter:
            counter[tier] += 1
        else:
            counter[tier] = 1
    return counter


def decide_fusion(target_tier, inventory, depth=0):
    if target_tier not in fusion_ranges: raise ValueError("Invalid target fusion tier")

    if p.SUPER == "shop":
        combos = COMBOS
        ranges = fusion_ranges
    else:
        combos = EXTRA
        ranges = super_ranges

    if p.WISHMAKING:
        combos += TWO_ITEM_COMBOS

    low, high = ranges[target_tier]
    valid_combos = [
        (combo, sum(item_points[t] for t in combo))
        for combo in combos
        if low <= sum(item_points[t] for t in combo) <= high
    ]
    
    best_choice = None
    best_missing = None
    best_missing_cost = None
    best_total_cost = None

    for combo, total in valid_combos:
        needed = combo_counter(combo)
        missing = {}
        missing_cost = 0
        for tier, count_needed in needed.items():
            have = len(inventory[tier])
            if have < count_needed:
                deficit = count_needed - have
                missing[tier] = deficit
                missing_cost += deficit * item_points[tier]
        
        if missing.get(4, 0) > 0: # never buy T4 for fusion
            continue
        if p.RUN_SCRIPT == "thrill" and missing.get(1, 0) > 0:
            # Thrill: never spend modules on T1 gifts.
            continue

        if p.SUPER == "shop" and not depth and missing.get(3, 0) == 1 and \
           sum([missing.get(i, 0) for i in range(1, 2)]) == 0:
            new_have = {tier: len(items) for tier, items in inventory.items()}
            skip_missing = True
            for i in range(1, 5):
                if i in needed.keys():
                    for _ in range(needed[i]):
                        if i == 3 and skip_missing:
                            skip_missing = False
                            continue
                        if new_have[i] > 0:
                            new_have[i] -= 1
            new_combo = None
            best_price = None
            for tier3_combo, price in get_tier3: # avoid recursion
                need = combo_counter(tier3_combo)
                for tier, count_needed in need.items():
                    if new_have[tier] < count_needed:
                        break
                else:
                    if best_price is None or price < best_price:
                        new_combo = tier3_combo
                        best_price = price
            if new_combo:
                combo = new_combo
                missing = {}
                missing_cost = 0
                total = total - item_points[3] + best_price

        if best_missing_cost is None        or \
           missing_cost < best_missing_cost or \
          (missing_cost == best_missing_cost and 
           total < best_total_cost):

            best_choice = combo
            best_missing = missing
            best_missing_cost = missing_cost
            best_total_cost = total

    return best_choice, best_missing


def is_in_range(res, coord):
    return res[0] - 103 < coord[0] < res[0] + 19 and res[1] - 105 < coord[1] < res[1] + 17

def inventory_check(reg, h, uptie_det=True):
    coords_agg = {1: [], 2: [], 3: [], 4: []}
    coords     = {1: [], 2: [], 3: [], 4: []}
    have = {}
    uptie = {}
    comp = p.WINDOW[2] / 1920

    fuse_shelf = screenshot(region=reg)
    image = amplify(fuse_shelf)

    for i in range(len(p.GIFTS)):
        if p.GIFTS[i]["sin"]:
            uptie_ego = p.GIFTS[i]["uptie1"] | p.GIFTS[i]["uptie2"] | (p.GIFTS[i]["uptie3"] if i != 0 else {})
        else:
            uptie_ego = {}

        for gift in p.GIFTS[i]["all"]:
            try:
                if gift in CACHE: template = CACHE[gift]
                else: template = amplify(cv2.imread(PTH[gift]))
                x, y = gui.center(LocateRGB.try_locate(template, image=image, region=reg, conf=0.87))
                have[gift] = (x, y, h)

                if uptie_det and gift in uptie_ego.keys():
                    uptie_region = fuse_shelf[int((y-66-reg[1])*comp):int((y-22-reg[1])*comp), int((x-14-reg[0])*comp):int((x+55-reg[0])*comp)]
                    try:
                        if not LocateRGB.check(PTH["+"], image=uptie_region, wait=False):
                            uptie[gift] = enhance_cost[uptie_ego[gift]]
                    except cv2.error:
                        print("Uptie detection failed")

                # THRILL: protect only thrill itself; other Rupture gifts stay
                # as fusion fuel. Other runs keep full team protection.
                if p.RUN_SCRIPT != "thrill" or gift == "thrill":
                    fuse_shelf = rectangle(fuse_shelf, (int(x - 62 - reg[0]), int(y - 72 - reg[1])), (int(x + 60 - reg[0]), int(y + 60 - reg[1])), (0, 0, 0), -1)
                    image = rectangle(image, (int(x - 62 - reg[0]), int(y - 72 - reg[1])), (int(x + 60 - reg[0]), int(y + 60 - reg[1])), (0, 0, 0), -1)
            except gui.ImageNotFoundException:
                continue

    for gift in list(p.KEYWORDLESS.keys()):
        try:
            if gift in CACHE: template = CACHE[gift]
            else: template = amplify(cv2.imread(PTH[gift]))
            x, y = gui.center(LocateRGB.try_locate(template, image=image, region=reg, conf=0.86))
            have[gift] = (x, y, h)

            if uptie_det and p.KEYWORDLESS[gift] > 2:
                uptie_region = fuse_shelf[int((y-66-reg[1])*comp):int((y-22-reg[1])*comp), int((x-14-reg[0])*comp):int((x+55-reg[0])*comp)]
                try:
                    if not LocateRGB.check(PTH["+"], image=uptie_region, wait=False):
                        uptie[gift] = enhance_cost[WORDLESS_MAP[gift]]
                except cv2.error:
                    print("Uptie detection failed")

            # THRILL: keywordless gifts also go into the fuel pool.
            if p.RUN_SCRIPT != "thrill":
                fuse_shelf = rectangle(fuse_shelf, (int(x - 62 - reg[0]), int(y - 72 - reg[1])), (int(x + 60 - reg[0]), int(y + 60 - reg[1])), (0, 0, 0), -1)
                image = rectangle(image, (int(x - 62 - reg[0]), int(y - 72 - reg[1])), (int(x + 60 - reg[0]), int(y + 60 - reg[1])), (0, 0, 0), -1)
        except gui.ImageNotFoundException:
            continue

    # SAIKAI: never let Spiderweb Entangled become fusion fuel. Not in any
    # team's "all" list, so black it out manually. Total miss is caught by the
    # fuse() guard, which skips fusion to stay safe.
    if p.RUN_SCRIPT == "saikai_ryoshu":
        for swt in sorted(k for k in PTH if k.lower().startswith("spider")):
            try:
                sweb = CACHE[swt] if swt in CACHE else amplify(cv2.imread(PTH[swt]))
                sx, sy = gui.center(LocateRGB.try_locate(sweb, image=image, region=reg, conf=0.80))
            except gui.ImageNotFoundException:
                continue
            have["spiderwebego"] = (sx, sy, h)
            fuse_shelf = rectangle(fuse_shelf, (int(sx - 62 - reg[0]), int(sy - 72 - reg[1])), (int(sx + 60 - reg[0]), int(sy + 60 - reg[1])), (0, 0, 0), -1)
            image = rectangle(image, (int(sx - 62 - reg[0]), int(sy - 72 - reg[1])), (int(sx + 60 - reg[0]), int(sy + 60 - reg[1])), (0, 0, 0), -1)
            logging.info("SAIKAI: Spiderweb located via %s at (%d, %d) - locked out of fusion fuel.", swt, sx, sy)
            break

    found_aff = []
    for aff in p.GIFTS:
        found_aff += [gui.center(box) for box in LocateRGB.locate_all(PTH[aff["checks"][4]], region=reg, image=fuse_shelf, threshold=50, method=cv2.TM_SQDIFF_NORMED)]

    for i in range(4, 0, -1):
        found = [gui.center(box) for box in LocateRGB.locate_all(PTH[str(i)], region=reg, image=fuse_shelf, threshold=50, method=cv2.TM_SQDIFF_NORMED)]

        for res in found:
            fuse_shelf = rectangle(fuse_shelf, (int(res[0] - 20 - reg[0]), int(res[1] - 22 - reg[1])), (int(res[0] + 102 - reg[0]), int(res[1] + 100 - reg[1])), (0, 0, 0), -1)
            x, y = res
            coords_agg[i].append((x, y, h))
            coords[i].append((x, y, h))

    for res in found_aff:
        for i in range(1, 5):
            match = next((coord for coord in coords[i] if is_in_range(res, coord)), None)
            if match:
                coords[i].remove(match)
                break

    return coords, coords_agg, have, uptie


def browse(hook_x, step=140, adj=0, dur=0.3):
    win_moveTo(hook_x, 480, tsize=(1, 1))
    win_dragTo(hook_x, 480 - step + adj, duration=dur, hook=True, tsize=(1, 1))

def browse_fast(hook_x, up=False):
    dy = -300 if not up else 300
    x_noise = random.randint(-50, 50)
    win_moveTo(hook_x + x_noise, 480)
    win_dragTo(hook_x, 480 + dy, duration=0.1)


def close_panel():
    if now.button(p.SUPER): return
    gui.press("esc")
    if not wait_while_condition(lambda: not now.button(p.SUPER), timer=1.5):
        gui.press("esc")
    time.sleep(0.1)
    x, y = win_get_position()
    if x > 750 and y < 830:
        win_moveTo(x, 841)

def concat(dict1, dict2):
    for key in dict2:
        if key in dict1:
            dict1[key].extend(dict2[key])
        else:
            dict1[key] = dict2[key]
    return dict1

def get_inventory():
    if getattr(p, "SKIP_EGO_CHECK", False):
        # Return empty dicts so callers' `in have` checks become no-ops.
        logging.info("Skipping get_inventory (Behaviour: Skip EGO check).")
        p.TO_UPTIE = {}
        return {}, {}, {}
    uptie = None
    hook_x = random.choice([1083, 1228, 1370, 1515])
    while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
        print("scroll down for inventory alignment")
        browse_fast(hook_x)
        time.sleep(0.5)

    if now_rgb.button("scroll.0"):
        h = 0
        adj = 0
        hook_x = random.choice([1083, 1228, 1370, 1515])
        while not now_rgb.button("scroll") and now_rgb.button("scroll", "scroll_full"):
            if h == 0:
                box = LocateGray.locate(PTH["gifts_owned"], region=REG["fuse_shelf"])
                region = REG["fuse_shelf"]
                if box:
                    _, y = gui.center(box)
                    y = max(295, min(777, y))
                    region = (920, y, 790, 777 - y)
                
                coords, coords_agg, have, uptie = inventory_check(region, 0)
                if box:
                    break
            else:
                print("scroll up for invetory scan")
                browse(hook_x, step=-140, adj=adj)

                if LocateGray.check(PTH["gifts_owned"], region=REG["fuse_shelf"], wait=False):
                    break
                
                new_coords, new_coords_agg, new_have, new_uptie = inventory_check(REG["fuse_shelf_peak"], h)
                coords = concat(coords, new_coords)
                coords_agg = concat(coords_agg, new_coords_agg)
                have.update(new_have)
                uptie.update(new_uptie)

                ck = LocateRGB.locate(PTH["height_ck"], region=(920, 585, 790, 165), method=1)
                adj = 625 - gui.center(ck)[1] if ck else 0
                print(adj)
            h += 1
    else:
        box = LocateGray.locate(PTH["gifts_owned"], region=REG["fuse_shelf"])
        region = REG["fuse_shelf"]
        if box:
            _, y = gui.center(box)
            y = max(295, min(777, y))
            region = (920, y, 790, 777 - y)
        
        coords, coords_agg, have, uptie = inventory_check(region, 0)
    
    if uptie is None:
        raise RuntimeError
    
    p.TO_UPTIE = uptie
    return coords, coords_agg, have


def actual_fuse(tier, coords):
    to_click = []
    combo, missing = decide_fusion(tier, coords)
    if not missing:
        for tier in combo:
            to_click.append(coords[tier][-1])
            coords[tier].pop(-1)
        perform_clicks(to_click)
        return None
    else: return missing

def fuse_selected():
    wait_while_condition(lambda: not now.button("Confirm.2"), lambda: win_click(1197, 876) if now.button("fuse") else None, timer=1.5)
    wait_while_condition(lambda: not now.button("Confirm"), lambda: gui.press("space") if now.button("Confirm.2") else None, timer=1.5)
    connection()
    wait_while_condition(
        lambda: loc.button("Confirm", wait=0.5), 
        lambda: gui.press("space"), 
        interval=0.2
    )

def perform_clicks(to_click):
    if p.WISHMAKING and not now_rgb.button("wishmaking"):
        time.sleep(0.1)
        wait_while_condition(lambda: not now.button("Confirm.0"), lambda: win_click(410, 755), interval=0.2, timer=0.2)
        wait_while_condition(lambda: now_click.button("Confirm.0"))
        win_moveTo(1194, 841)
        time.sleep(0.2)

    hook_x = random.choice([1083, 1228, 1370, 1515])
    while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
        print("scroll down for inventory click alignment")
        browse_fast(hook_x)
        time.sleep(0.5)

    to_click = sorted(to_click, key=lambda x: x[2])
    h = 0
    adj = 0
    for pos in to_click:
        if pos[2] - h > 0:
            print("iterating items for fuse")
            for _ in range(pos[2] - h):
                browse(hook_x, step=-135, adj=adj)
                ck = LocateRGB.locate(PTH["height_ck"], region=REG["fuse_shelf_low"])
                adj = 625 - gui.center(ck)[1] if ck else 0
            h = pos[2]
            time.sleep(0.2)
        ClickAction(pos[:2], ver="forecast!").execute(click_rgb)
    
    fuse_selected()
    to_click.clear()

    hook_x = random.choice([1083, 1228, 1370, 1515])
    while not now_rgb.button("scroll") and now_rgb.button("scroll", "scroll_full"):
        print("scroll up for alignment")
        browse_fast(hook_x, up=True)
        time.sleep(0.5)


def set_affinity(i, teams=None):
    if teams is None: teams = p.GIFTS
    if p.IDX == i: return
    p.IDX = i
    ClickAction((469, 602), ver="keywordSel").execute(shop_click)
    win_moveTo(605, 612)
    confirm_affinity(teams=teams)
    time.sleep(0.2)

def search_have(have, fuse_type, idx):
    missing = 0
    iterations = 0
    names = []
    if name := next((key for key, value in p.GIFTS[idx][f"fuse{fuse_type + 1}"].items() if value is None), None):
        if name in have:
            iterations += 2
        else:
            names += list(p.GIFTS[idx][f"fuse{fuse_type}"].keys())

    names += [key for key, value in p.GIFTS[idx][f"fuse{fuse_type + 1}"].items() if value is not None]
    for name in names:
        if name not in have.keys():
                missing += 1
        iterations += 1
    return missing/iterations

def fuse_search(have):
    # SAIKAI only wants the two T4 powerful-ego fusions; no recipe chasing.
    if p.RUN_SCRIPT == "saikai_ryoshu":
        return []
    advanced_fusing = []
    if p.GIFTS[0]["sin"] and not p.GIFTS[0]["goal"][0] in have.keys():
        advanced_fusing.append((0, search_have(have, 1, 0), 1))
    if p.HARD and p.GIFTS[0]["sin"] and len(p.GIFTS[0]["goal"]) > 1 \
       and not p.GIFTS[0]["goal"][1] in have.keys():
        advanced_fusing.append((0, search_have(have, 3, 0), 3))
    advanced_fusing.sort(key=lambda item: (item[1], item[0]))
    return advanced_fusing


# fusion_available = (928, 304, 300, 82)
def get_gifts(gifts, reg, is_fuse=False):
    if not is_fuse:
        fuse_shelf = screenshot(region=reg)
        image = amplify(fuse_shelf)

    for gift in gifts:
        if is_fuse:
            fuse_shelf = screenshot(region=reg)
            image = amplify(fuse_shelf)
        try:
            if gift in CACHE: template = CACHE[gift]
            else: template = amplify(cv2.imread(PTH[gift]))
            x, y = gui.center(LocateRGB.try_locate(template, image=image, region=reg, conf=0.88))
            print(f'got {gift}')
            yield (x, y)
        except gui.ImageNotFoundException:
            continue

def click_gifts(gifts, reg, chain=None, is_fuse=False):
    if is_fuse and LocateGray.check(PTH["gifts_owned"], region=REG["gifts_owned"], wait=False):
        return True
    
    gift_searcher = get_gifts(gifts, reg, is_fuse=is_fuse)
    for coord in gift_searcher:
        ignore = LocateRGB.locate_all(PTH["cannot_fuse"], region=reg, threshold=80)
        print(ignore)
        if any(abs(gui.center(res)[0] - coord[0]) < 50 for res in ignore):
            continue

        print('got a gift for fusion!')
        win_click(coord)
        if chain is not None and callable(chain):
            chain()
        time.sleep(0.2)
        if is_fuse and LocateGray.check(PTH["gifts_owned"], region=REG["gifts_owned"], wait=False):
            print("all fused!")
            return True
    return False

def get_fuse_list():
    gift_list = p.GIFTS[0]["goal"]

    for i in range(2, 5, 2):
        if not p.GIFTS[0].get(f"fuse{i}", False):
            continue
        gift_list += [name for name, tier in p.GIFTS[0][f"fuse{i}"].items() if tier is None]
    return gift_list    

def handle_available_fusion():
    print("checking available fusion...")
    hook_x = random.choice([1083, 1228, 1370, 1515])
    while not now_rgb.button("scroll") and now_rgb.button("scroll", "scroll_full"):
        print("scroll up for alignment")
        browse_fast(hook_x, up=True)
        time.sleep(0.5)

    if not now_rgb.button("fusion_available"):
        return now_rgb.button("scroll", "scroll_full")
    
    gift_list = get_fuse_list()
    print(f"gifts to fuse: {gift_list}")
    if not gift_list: return now_rgb.button("scroll", "scroll_full")
    
    if click_gifts(gift_list, REG["fuse_shelf_top"], chain=fuse_selected, is_fuse=True):
        return now_rgb.button("scroll", "scroll_full")
    
    if now_rgb.button("scroll", "scroll_full"):
        h = 1
        adj = 0
        hook_x = random.choice([1083, 1228, 1370, 1515])
        while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
            print("scroll down for available fusions tab")
            browse(hook_x, adj=adj)
            if click_gifts(gift_list, REG["fuse_shelf_top"], chain=fuse_selected, is_fuse=True):
                return now_rgb.button("scroll", "scroll_full")
            ck = LocateRGB.locate(PTH["height_ck"], region=REG["fuse_shelf_top"])
            adj = 625 - gui.center(ck)[1] if ck else 0
            h += 1
    return False


def fuse():
    time.sleep(0.2)

    if handle_available_fusion():
        hook_x = random.choice([1083, 1228, 1370, 1515])
        while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
            print("scroll down for invetory scan alignment")
            browse_fast(hook_x)
            time.sleep(0.5)
    
    coords, coords_agg, have = get_inventory()
    # THRILL: once Thrill is in inventory, exit so fuse_loop skips F2/F3 markets.
    if p.RUN_SCRIPT == "thrill" and "thrill" in have:
        if not getattr(p, "THRILL_DONE", False):
            logging.info("THRILL: thrill EGO gift confirmed in inventory.")
        p.THRILL_DONE = True
        raise NotImplementedError
    # SAIKAI: if Spiderweb wasn't located (not blacked out), stop fusing rather
    # than risk consuming it. Raises the loop's clean "done" exit.
    if p.RUN_SCRIPT == "saikai_ryoshu" and "spiderwebego" not in have:
        logging.warning("SAIKAI: Spiderweb NOT found in fuse inventory - stopping fusion "
                        "this shop so it can never be used as fuel (check the template if this keeps firing).")
        raise NotImplementedError
    to_click = []
    fuse_type = 0
    got_all = False
    advanced_fusing = fuse_search(have)

    if p.EXTREME: coords_agg = coords

    # get powerful ego gift
    for i in range(len(p.GIFTS)):
        if not list(p.GIFTS[i]["uptie2"].keys())[0] in have.keys():
            _, missing = decide_fusion(4, coords_agg)
            if missing: 
                if i == 0 or not advanced_fusing:
                    return missing
                else:
                    break
            else:
                set_affinity(i)
                actual_fuse(4, coords_agg)
                return None
    else:
        got_all = True

    # get recipe ego gifts
    if advanced_fusing:
        i, _, fuse_type = advanced_fusing[0]
        set_affinity(i)
    elif got_all:
        if p.RUN_SCRIPT == "saikai_ryoshu":
            # Both T4s done; we want NO other fusions.
            raise NotImplementedError
        for i in range(len(p.GIFTS)):
            for name, tier in p.GIFTS[i]["fuse_ex"].items():
                if not name in have.keys():
                    set_affinity(i)
                    missing = actual_fuse(tier, coords)
                    return missing

        # lunar memory
        if p.EXTREME and not "lunarmemory" in have.keys():
            teams = list(TEAMS.values())
            for i in range(7, 10):
                if not list(teams[i]["uptie2"].keys())[0] in have.keys():
                    set_affinity(i, teams=teams)
                    missing = actual_fuse(4, coords)
                    return missing
                to_click.append(have[list(teams[i]["uptie2"].keys())[0]])
            stones_have = list(set([f"stone{i}" for i in range(7)]) & set(have.keys()))
            if len(stones_have) < 2:
                for i in range(7):
                    if not f"stone{i}" in have.keys():
                        set_affinity(i, teams=teams)
                        missing = actual_fuse(4, coords)
                        return missing
            for i in range(2):
                to_click.append(have[stones_have[i]])
            if p.SUPER == "supershop":
                perform_clicks(to_click)
            return None
        raise NotImplementedError
    else:
        return None

    if fuse_type:
        for name, tier in p.GIFTS[p.IDX][f"fuse{fuse_type+1}"].items():
            if not name in have.keys():
                if tier != None:
                    missing = actual_fuse(tier, coords)
                    return missing
                else: # fuse the predecessor first
                    for name, tier in p.GIFTS[p.IDX][f"fuse{fuse_type}"].items():
                        if not name in have.keys():
                            missing = actual_fuse(tier, coords)
                            return missing
                        to_click.append(have[name])
                    perform_clicks(to_click)
                    return None
            to_click.append(have[name])
        perform_clicks(to_click)

    return None


def confirm_affinity(teams=None):
    if teams is None: teams = p.GIFTS
    if not (0 <= p.IDX < len(teams)): p.IDX = 0
    is_not_seleted = True
    while is_not_seleted:
        click_rgb.button(teams[p.IDX]["checks"][3], "affinity!")
        win_click(1194, 841, tsize=(100, 30))
        time.sleep(0.1)
        if not now.button("notSelected"):
            is_not_seleted = False
        else:
            ClickAction((469, 602), ver="keywordSel").execute(shop_click)

def init_fuse():
    chain_actions(shop_click, [
        Action(p.SUPER, click=(410, 580), ver="fuse"),
        lambda: time.sleep(0.1),
        ClickAction((469, 602), ver="keywordSel")
    ])
    win_moveTo(605, 612)
    confirm_affinity()

def fuse_loop():
    if getattr(p, "SKIP_EGO_FUSION", False):
        logging.info("Skipping fuse_loop (Behaviour: Skip EGO fusion).")
        return
    # THRILL: once Thrill is crafted on F1, skip fusion on F2/F3.
    if (p.RUN_SCRIPT == "thrill" and getattr(p, "THRILL_DONE", False)
            and p.LVL >= 2):
        logging.info("THRILL: thrill already crafted - skipping fuse on floor %d.", p.LVL)
        return
    init_fuse()
    ehnance_flag = True
    ref_count = 1 + (p.BUFF[5] > 2)
    try:
        while True:
            try:
                missing = fuse()
            except NotImplementedError:
                # fuse()'s clean "done fusing" signal. Re-raise so the
                # `except RuntimeError` below doesn't swallow it (it subclasses RuntimeError).
                raise
            except RuntimeError:
                print("oops")
                close_panel()
                continue

            if missing:
                close_panel()

                if ehnance_flag and p.TO_UPTIE:
                    # THRILL: only thrill itself gets enhanced (in thrill_market_f1).
                    if p.RUN_SCRIPT != "thrill":
                        enhance(p.TO_UPTIE)
                    ehnance_flag = False

                if len(LocateRGB.locate_all(PTH["purchased"], region=REG["buy_shelf"], threshold=100)) == 8: return

                # THRILL: skip the module-costing keyword refresh.
                kw_ref = False if p.RUN_SCRIPT == "thrill" else (ref_count > 0)
                result = buy_loop(missing, keyword_ref=kw_ref)
                ref_count -= 1
                if not result:
                    if p.RUN_SCRIPT == "thrill":
                        # F1 MUST craft thrill: keep retrying until success or
                        # budget-out (RuntimeError hard-fails the run).
                        while not result:
                            try:
                                bal = balance()
                            except Exception:
                                bal = 0
                            if bal < 200:
                                logging.error("THRILL: F1 market - budget out "
                                              "(bal=%s) without crafting thrill. "
                                              "RUN FAILED.", bal)
                                raise RuntimeError(
                                    "THRILL: market could not buy fuel - run failed")
                            logging.info("THRILL: shelf refresh (bal=%s) - "
                                         "retry buy %s.", bal, missing)
                            win_click(1489, 177, tsize=(180, 53))
                            connection()
                            time.sleep(0.3)
                            result, missing = buy(missing)
                    else:
                        return
                init_fuse() # open fusing (success path for both branches)
    except NotImplementedError:
        close_panel()

        # THRILL handles its own enhance and wants no extra buys.
        if p.RUN_SCRIPT == "thrill":
            return

        if p.TO_UPTIE:
            enhance(p.TO_UPTIE)

        buy_some(2 + 2*(p.LVL < 11))


def thrill_market_f1():
    """F1 market flow for the Thrill scripted run: skip uptie1 enhance, buy
    T3 (fall back to T2), let fuse_loop craft Thrill, then enhance Thrill."""
    logging.info("THRILL: F1 market - starting.")

    # Close the upgrade menu opened on shop entry (Thrill skips uptie1 enhance).
    close_panel()
    time.sleep(0.3)

    # T3 first, fall back to T2. floor1=False so the refresh only runs on a
    # failed buy. keyword_ref=False skips the module-costing keyword refresh.
    try:
        bought_t3 = buy_loop({3: 1}, keyword_ref=False)
        if bought_t3:
            logging.info("THRILL: F1 - T3 bought (Case II).")
        else:
            logging.info("THRILL: F1 - no T3 in shop, buying T2 (Case I).")
            buy_loop({2: 4}, keyword_ref=False)
    except Exception as exc:
        logging.warning("THRILL: F1 - buy phase errored: %s", exc)

    # Fuse phase. RuntimeError (budget-out) MUST propagate to hard-fail the run;
    # other exceptions are caught so a flaky frame doesn't nuke an otherwise fine run.
    try:
        fuse_loop()
    except RuntimeError:
        raise
    except Exception as exc:
        logging.warning("THRILL: F1 - fuse_loop hit non-fatal error: %s", exc)

    # If thrill isn't in inventory, set the F1 RESTART flag; main_loop runs the
    # no-claim forfeit and emits tele.restart() so the run lists as "Restart".
    if not getattr(p, "THRILL_DONE", False):
        logging.error("THRILL: F1 market exited without crafting thrill. "
                      "Triggering F1 RESTART (no claim).")
        p.THRILL_F1_RESTART = True
        return

    logging.info("THRILL: F1 - enhancing thrill (only).")
    try:
        ClickAction((250, 581), ver="power").execute(click)
        enhance({"thrill": 4}, floor1=True)
    except Exception as exc:
        logging.warning("THRILL: F1 - thrill enhance failed: %s", exc)


def power_up():
    for _ in range(2):
        wait_while_condition(lambda: not now.button("Confirm.2"), lambda: gui.press("space"), timer=1.5)
        wait_while_condition(lambda: not now.button("power"), lambda: gui.press("space"), timer=1.5)

def get_uptie_inventory(gift_list):
    click_gifts(gift_list, REG["fuse_shelf"], chain=power_up)
    if now_rgb.button("scroll", "scroll_full"):
        h = 1
        adj = 0
        hook_x = random.choice([1083, 1228, 1370, 1515])
        while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
            print("scroll down for enhance click")
            browse(hook_x, adj=adj)
            click_gifts(gift_list, REG["fuse_shelf_low"], chain=power_up)
            ck = LocateRGB.locate(PTH["height_ck"], region=REG["fuse_shelf_low"])
            adj = 625 - gui.center(ck)[1] if ck else 0
            h += 1

def search_sell(reg):
    coords, _, _, _ = inventory_check(reg, 0, uptie_det=True)
    for i in range(4, 0, -1):
        if coords[i] != []:
            win_click(coords[i][0][:2])
            time.sleep(0.2)
            wait_while_condition(lambda: not now.button("Confirm_retry.0"), lambda: gui.press("space"), timer=1.5)
            wait_while_condition(lambda: not now.button("connecting"), lambda: gui.press("space"), timer=1.5)
            connection()
            close_panel()
            return True
    return False

def sell(gifts):
    while True:
        if balance() < sum(gifts.values()):
            Action(p.SUPER, click=(600, 585), ver="sell").execute(click)
            found_flag = False
            if search_sell((920, 295, 790, 345)):
                found_flag = True
            elif now_rgb.button("scroll", "scroll_full"):
                hook_x = random.choice([1088, 1226, 1364, 1501])
                while not now_rgb.button("scroll.0") and now_rgb.button("scroll", "scroll_full"):
                    print("scroll down for sell scan")
                    browse_fast(hook_x)
                    time.sleep(0.5)
                adj = 0
                hook_x = random.choice([1088, 1226, 1364, 1501])
                while not now_rgb.button("scroll") and now_rgb.button("scroll", "scroll_full"):
                    if search_sell((920, 585, 790, 165)):
                        found_flag = True
                        break
                    print("scroll up for sell click")
                    browse(hook_x, step=-165, adj=adj)
                    ck = LocateRGB.locate(PTH["height_ck"], region=(920, 585, 790, 165))
                    adj = 618 - gui.center(ck)[1] if ck else 0
            
            if found_flag: continue

            close_panel()
            return False
        else:
            return True

def check_ehance_cost(gifts):
    if not sell(gifts):
        cost = balance()
        uptie = []
        for k, v in gifts.items():
            cost -= v
            if cost > 0:
                uptie.append(k)
            else:
                break
    else:
        uptie = list(gifts.keys())
    return uptie


def enhance(gifts, floor1=False):
    if getattr(p, "SKIP_EGO_ENHANCING", False):
        logging.info("Skipping enhance (Behaviour: Skip EGO enhancing).")
        return
    if not floor1:
        gift_list = check_ehance_cost(gifts)
        if not gift_list: return

        ClickAction((250, 581), ver="power").execute(click)
    else:
        gift_list = [k for k in gifts.keys()]

    get_uptie_inventory(gift_list)
    close_panel()
    time.sleep(0.3)


def balance():
    answer_me = True
    bal = -1
    start_time = time.time()
    while bal == -1:
        if time.time() - start_time > 20: raise RuntimeError("Infinite loop exited")
        digits = []
        for i in range(9, -1, -1):
            pos = [gui.center(box) for box in LocateRGB.locate_all(PTH[f"cost{i}"], region=(857, 175, 99, 57), threshold=7, conf=0.9, method=cv2.TM_SQDIFF_NORMED)]
            for coord in pos:
                if all(abs(coord[0] - existing_coord) > 7 for _, existing_coord in digits):
                    digits.append((i, coord[0]))
        digits = sorted(digits, key=lambda x: x[1])

        bal = ""
        for i in digits: bal += str(i[0])
        bal = int(bal or -1)
        if bal != -1 and bal < 300 and answer_me:
            time.sleep(0.2)
            answer_me = False # low reading may be mid-update; re-read
            bal = -1
    print("money", bal)
    if p.LVL > 10:
        bal = apply_inflation(bal)
    return bal

def apply_inflation(value):
    if 13 > p.LVL > 10:
        value = value // 2
    elif p.LVL >= 13:
        value = value // 3
    return value

def conf_gift():
    try:
        Action("purchase", ver="connecting").execute(click)
        connection()
    except RuntimeError:
        pass
    
    input_with_fallback(
        "space", 
        lambda: now_click.button("Confirm"),
        lambda: wait_while_condition(
            lambda: loc.button("Confirm", wait=0.5),
            timer=2
        )
    )

def update_shelf():
    shop_shelf = screenshot(region=REG["buy_shelf"])
    shop_shelf = rectangle(shop_shelf, (52, 33), (224, 195), (0, 0, 0), -1)
    for ignore in ["purchased", "cost"]:
        found = [gui.center(box) for box in LocateRGB.locate_all(PTH[str(ignore)], region=REG["buy_shelf"], image=shop_shelf, threshold=20)]
        for res in found:
            shop_shelf = rectangle(shop_shelf, (int(res[0] - 70 - 809), int(res[1] - 25 - 300)), (int(res[0] + 70 - 809), int(res[1] + 150 - 300)), (0, 0, 0), -1)
    return shop_shelf

def filter_x_distance(points, x_tol=2, y_tol=25):
    points = sorted(points, key=lambda p: p[0])
    result = []
    for p in points:
        if all(abs(p[0] - q[0]) >= x_tol or abs(p[1] - q[1]) > y_tol for q in result):
            result.append(p)
    return result

def get_shop(shop_shelf):
    tier1 = [gui.center(box) for box in LocateRGB.locate_all(PTH["buy1"], region=REG["buy_shelf"], image=shop_shelf, threshold=3.5, conf=0.92, method=cv2.TM_SQDIFF_NORMED)]
    tier4 = [gui.center(box) for box in LocateRGB.locate_all(PTH["buy4"], region=REG["buy_shelf"], image=shop_shelf, threshold=10, conf=0.92, method=cv2.TM_SQDIFF_NORMED)]
    tier1 = filter_x_distance(tier1)
    have = {1: [], 2: [], 3: []}
    visited = set()
    for i, pt_i in enumerate(tier1):
        if i in visited: continue
        count = 1
        for j in range(i + 1, len(tier1)):
            pt_j = tier1[j]
            if all(abs(pt_i[k] - pt_j[k]) <= 25 for k in range(2)):
                visited.add(j)
                count += 1
        have[min(count, 3)].append(pt_i)
    have[1] = [
        (fx, fy) for (fx, fy) in have[1]
        if not any(abs(fx - x) <= 25 and abs(fy - y) <= 25 for (x, y) in tier4)
    ]
    return have


def buy_known(aff):
    shop_shelf = update_shelf()
    output = False
    for gift in aff["buy"]:
        try:
            res = gui.center(LocateRGB.try_locate(PTH[gift], image=shop_shelf, region=REG["buy_shelf"], comp=0.75, conf=0.83))
            print(f'got {gift}')
            win_click(res, tsize=(90, 90))
            conf_gift()
            time.sleep(0.1)
            shop_shelf = update_shelf()
            output = True
        except gui.ImageNotFoundException:
            continue
    return shop_shelf, output

def buy_affinity(aff):
    box = True
    while box:
        shop_shelf = update_shelf()
        box = LocateRGB.locate(PTH[aff["checks"][0]], region=REG["buy_shelf"], image=shop_shelf, method=cv2.TM_SQDIFF_NORMED, comp=0.88, conf=0.8)
        if box: 
            res = gui.center(box)
            win_click(res)
            conf_gift()
            time.sleep(0.1)
    return shop_shelf, False

def buy_some(rerolls=1, priority=False):
    if getattr(p, "SKIP_EGO_BUYING", False):
        logging.info("Skipping buy_some (Behaviour: Skip EGO buying).")
        return
    time.sleep(0.2)
    iterations = rerolls + 1
    keywordless = [{"buy": [name for name, state in p.KEYWORDLESS.items() if state > 1], "sin": True}]
    sold_all = False
    for _ in range(iterations):
        if not priority and not sold_all and balance() < 200:
            sold_all = not sell({"all": 300})
        if p.EXTREME:
            for _ in range(1 + int(p.SUPER == "supershop")):
                buy_skill3()
        # SAIKAI: grab the build's key poise gifts FIRST, ahead of every other gift.
        # Filtered to installed templates so a missing PNG never KeyErrors.
        if p.RUN_SCRIPT == "saikai_ryoshu":
            saikai_buy = [g for g in ("emeraldelytra", "endorphinkit", "nebulizer") if g in PTH]
            if saikai_buy:
                buy_known({"buy": saikai_buy})
        for aff in keywordless + p.GIFTS:
            if not priority or not aff["sin"]:
                if "checks" in aff:
                    buy_affinity(aff)
                else:
                    buy_known(aff)
            else: # priority pass: only necessary gifts
                buy_known(aff)
        if len(LocateRGB.locate_all(PTH["purchased"], region=REG["buy_shelf"], threshold=100)) == 8: break
        if rerolls and balance() >= 200:
            rerolls -= 1
            win_click(1489, 177, tsize=(180, 53))
            connection()
            time.sleep(0.1)
            if p.RUN_SCRIPT == "saikai_ryoshu":
                saikai_skill_replace()          # Ryoshu only; never the generic path
            else:
                do_skill_replace()
        elif balance() < 120: return

def buy(missing):
    output = False
    keywordless = [{"buy": [name for name, state in p.KEYWORDLESS.items() if state > 1], "sin": True}]
    for aff in keywordless + p.GIFTS:
        if aff["sin"]:
            shop_shelf, out = buy_known(aff)
        else:
            shop_shelf, out = buy_affinity(aff)
        if out: output = True

    if output: return True, missing # got the build

    gained = {1: 0, 2: 0, 3: 0}
    for tier in sorted(missing.keys(), reverse=True):
        for _ in range(missing[tier]):
            have = get_shop(shop_shelf)
            print(f'got {have}')
            if have[tier]:
                win_click(have[tier][0])
                conf_gift()
                shop_shelf = update_shelf()
                gained[tier] += 1
            else:
                return output, {key: missing[key] - gained[key] for key in missing}
    return True, {}

def buy_loop(missing, floor1=False, keyword_ref=True):
    if getattr(p, "SKIP_EGO_BUYING", False):
        logging.info("Skipping buy_loop (Behaviour: Skip EGO buying).")
        return
    print("need", missing)
    result, missing = buy(missing)
    if not result or floor1:
        try: 
            if keyword_ref and ((bal:= balance()) >= 300 or bal >= 200 and p.BUFF[5] > 0):
                Action(p.SUPER, click=(1715, 176), ver="keywordRef").execute(shop_click)
                wait_while_condition(
                    condition=lambda: now.button("keywordRef") and not now.button("connecting"), 
                    action=confirm_affinity
                )
                connection()
                if p.RUN_SCRIPT == "saikai_ryoshu":
                    saikai_skill_replace()      # Ryoshu only; never the generic path
                else:
                    do_skill_replace()
                if p.EXTREME:
                    time.sleep(0.2)
                    for _ in range(1 + int(p.SUPER == "supershop")):
                        buy_skill3()

                result, missing = buy(missing)

            if (not result or floor1) and balance() >= 200:
                win_click(1489, 177, tsize=(180, 53))
                connection()
                time.sleep(0.1)
                if p.RUN_SCRIPT == "saikai_ryoshu":
                    saikai_skill_replace()      # Ryoshu only; never the generic path
                else:
                    do_skill_replace()
                if p.EXTREME:
                    time.sleep(0.2)
                    for _ in range(1 + int(p.SUPER == "supershop")):
                        buy_skill3()

                new_result, _ = buy(missing)
                result = result or new_result
        except RuntimeError:
            print("no cash, sorry")
    return result


def buy_skill3():
    if balance() <= 120: 
        return
    
    if (p.SUPER == "shop" and 
       (now.button("purchased") or 
        now.button("cost", "purchased"))): 
        return
    
    sold = []
    if p.SUPER == "supershop":
        sold = LocateGray.locate_all(PTH["purchased"], region=REG["purchased_sup!"])
        if now.button("cost", "purchased_sup!") or len(sold) >= 2:
            return

    coord = None
    for sinner in p.SELECTED[:7]:
        box = LocateGray.locate(PTH[f"{sinner.lower()}_s3"], region=REG["buy_s3"], conf=0.85)
        if box:
            coord = gui.center(box)
            if len(sold) > 0:
                sold_coord = gui.center(sold[0])
                if abs(coord[0] - sold_coord[0]) < 100:
                    continue
            break
    else:
        return
    
    if coord == None or coord[1] - 120 < 0:
        return

    ClickAction((coord[0], coord[1] - 120), ver="replace").execute(click)
    win_click(1442, 497)
    win_click(1187, 798)
    if not wait_while_condition(lambda: not loc.button("connecting", wait=0.5), lambda: win_click(1187, 798), timer=1):
        win_click(953, 497)
        win_click(1187, 798)
        if not wait_while_condition(lambda: not loc.button("connecting", wait=0.5), lambda: win_click(1187, 798), timer=2):
            win_click(772, 800)
            return
    connection()


def revive_idiots():
    if getattr(p, "SKIP_SINNER_HEALING", False):
        logging.info("Skipping revive_idiots (Behaviour: Skip sinner healing).")
        return
    revivals = min(p.DEAD, balance()//100)
    if revivals < 1: return
    
    ClickAction((293, 705), ver="return").execute(click)
    for _ in range(revivals):
        if not wait_while_condition(lambda: now.button("return"), lambda: win_click(1545, 690), timer=3):
            Action("return", ver=p.SUPER).execute(click)
            return
        Action("no_hp", ver="select").execute(click_rgb)
        Action("select", ver="connecting").execute(click)
        connection()
        ClickAction((1545, 500), ver="return").execute(click)
        time.sleep(0.2)
    Action("return", ver=p.SUPER).execute(click)
    time.sleep(0.2)

def heal_all():
    if getattr(p, "SKIP_SINNER_HEALING", False):
        logging.info("Skipping heal_all (Behaviour: Skip sinner healing).")
        return
    if balance() < 100: return

    ClickAction((293, 705), ver="return").execute(click)
    try:
        ClickAction((1545, 500), ver="connecting").execute(click)
        connection()
        time.sleep(0.2)
    finally:
        ClickAction((1545, 500), ver="return").execute(click)
        Action("return", ver=p.SUPER).execute(click)
        time.sleep(0.2)

def leave():
    ClickAction((1705, 967), ver="ConfirmInvert").execute(click)
    wait_while_condition(lambda: loc.button("ConfirmInvert", wait=0.5), lambda: gui.press("space"), interval=1, timer=5)
    wait_while_condition(lambda: now.button(p.SUPER), timer=5)


# --- Generic Skill Replacement (all 12 sinners) ----------------------------
# Driven by p.SKILL_REPLACE_* (active set, priority, run quota, per-shop counters).
# shop() resets the per-shop counters; execute_me seeds the run quota.

# UI label -> PTH stem for the shop offer card template.
_SKILL_REPLACE_OFFERS = {
    "Yi Sang":     "srep_yisang",
    "Faust":       "srep_faust",
    "Don Quixote": "srep_donquixote",
    "Ryōshū":      "srep_ryoshu",
    "Meursault":   "srep_meursault",
    "Hong Lu":     "srep_honglu",
    "Heathcliff":  "srep_heathcliff",
    "Ishmael":     "srep_ishmael",
    "Rodion":      "srep_rodion",
    "Sinclair":    "srep_sinclair",
    "Outis":       "srep_outis",
    "Gregor":      "srep_gregor",
}

# Swap-key (UI stored value) -> PTH stem for the in-menu button.
_SKILL_REPLACE_SWAPS_PTH = {
    "1>2": "srep_swap12",
    "1>3": "srep_swap13",
    "2>3": "srep_swap23",
}

_SKILL_REPLACE_MENU = "srep_menu"

# Offer artwork is the LABEL strip below the clickable button (~this many px above the template centre).
_SKILL_REPLACE_BUTTON_Y_OFFSET = 110


def _skill_replace_cap_for_super(super_kind: str) -> int:
    """Distinct sinners that may be swapped during one shop visit (1 normal, 2 super)."""
    return 2 if super_kind == "supershop" else 1


def _scan_active_sinner_offer():
    """Probe for the first ACTIVE sinner whose offer is on screen and not yet
    swapped this visit. Returns (sinner_name, template_stem, box) or all-None."""
    active = getattr(p, "SKILL_REPLACE_ACTIVE", None) or set()
    done = getattr(p, "SKILL_REPLACE_SINNERS_THIS_SHOP", None) or set()
    # Deterministic order so retries probe the same sinner first.
    pending = sorted(s for s in active if s not in done)
    skipped_already_done = sorted(s for s in active if s in done)
    skipped_no_template = []
    for sinner_name in pending:
        tpl = _SKILL_REPLACE_OFFERS.get(sinner_name)
        if not tpl or tpl not in PTH:
            skipped_no_template.append(sinner_name)
            continue
        # Fullscreen probe (gray then RGB) at 0.80. The offer banner can render
        # outside REG["buy_shelf"]; the slack lets tinted cards through.
        box = LocateGray.locate(PTH[tpl], conf=0.80)
        if box is None:
            box = LocateRGB.locate(PTH[tpl], conf=0.80)
        if box:
            return sinner_name, tpl, box
    logging.debug(
        "Skill replace scan: nothing matched. active=%d, pending=%s, "
        "already-this-shop=%s, missing-template=%s",
        len(active), pending, skipped_already_done, skipped_no_template)
    return None, None, None


def _pick_swap_with_quota(sinner_name: str):
    """Return the first swap-key in this sinner's priority list whose run quota
    is still > 0, or None when every priority entry is exhausted."""
    order = (getattr(p, "SKILL_REPLACE_ORDER", None) or {}).get(sinner_name, [])
    remaining = (getattr(p, "SKILL_REPLACE_REMAINING", None) or {}).get(sinner_name, {})
    for key in order:
        try:
            if int(remaining.get(key, 0) or 0) > 0:
                return key
        except (TypeError, ValueError):
            continue
    return None


def _wait_for_skill_replace_menu(timeout_s: float = 5.0) -> bool:
    """Block until the swap menu is visible or `timeout_s` elapses. Tries gray
    then RGB at the same conf since a tinted overlay can drop gray below 0.9."""
    if _SKILL_REPLACE_MENU not in PTH:
        return False
    deadline = max(1, int(timeout_s / 0.2))
    tpl = PTH[_SKILL_REPLACE_MENU]
    for _ in range(deadline):
        if LocateGray.check(tpl, wait=False, conf=0.85):
            return True
        if LocateRGB.check(tpl, wait=False, conf=0.85):
            return True
        time.sleep(0.2)
    return False


def do_skill_replace():
    """Take a skill-swap offer for an active sinner on the shop shelf.
    Returns the swap count taken (0..2). Per-shop cap: 1 for shop, 2 for supershop."""
    if not getattr(p, "SKILL_REPLACE_ACTIVE", None):
        return 0
    if _SKILL_REPLACE_MENU not in PTH:
        # Without the menu detector, no way to confirm we opened the swap UI.
        return 0

    cap = _skill_replace_cap_for_super(p.SUPER)
    if getattr(p, "SKILL_REPLACE_USED_THIS_SHOP", 0) >= cap:
        return 0

    swaps_taken = 0
    # Re-probe each iteration: a successful swap may expose a 2nd offer.
    while (getattr(p, "SKILL_REPLACE_USED_THIS_SHOP", 0) + swaps_taken) < cap:
        sinner_name, tpl, box = _scan_active_sinner_offer()
        if sinner_name is None:
            break

        # Quota gate FIRST. An ESC-to-back-out after opening the menu would
        # leak onto the dungeon overlay and break dungeon_start with an
        # infinite Initialization-error loop.
        chosen = _pick_swap_with_quota(sinner_name)
        if chosen is None:
            logging.info(
                "Skill replace: %s priority list exhausted for this run; "
                "skipping (menu NOT opened).", sinner_name)
            p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
            continue

        # Detected template is the LABEL strip; the button sits ~110px above.
        center_x, center_y = gui.center(box)
        click_x = center_x
        click_y = center_y - _SKILL_REPLACE_BUTTON_Y_OFFSET
        logging.info(
            "Skill replace: opening %s offer for %s (template center "
            "(%d, %d), click target (%d, %d)).",
            sinner_name, chosen, center_x, center_y, click_x, click_y)
        win_click(click_x, click_y, tsize=(10, 10))
        time.sleep(0.6)

        if not _wait_for_skill_replace_menu(timeout_s=3.0):
            logging.warning(
                "Skill replace: opened %s offer but the swap menu did not appear.",
                sinner_name)
            p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
            continue

        swap_tpl = _SKILL_REPLACE_SWAPS_PTH.get(chosen)
        if not swap_tpl or swap_tpl not in PTH:
            logging.warning(
                "Skill replace: missing template for swap %r; closing menu.",
                chosen)
            gui.press("escape")
            time.sleep(0.4)
            p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
            continue

        if not tap_center(swap_tpl, tsize=(46, 22), wait=3):
            logging.warning(
                "Skill replace: %s %s button not visible inside the menu.",
                sinner_name, chosen)
            gui.press("escape")
            time.sleep(0.4)
            p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
            continue

        # Two-stage confirm dialog: the game shows it twice (preview then commit).
        time.sleep(0.5)
        confirms = 0
        for n in range(2):
            if not tap_center("packconfirm", tsize=(60, 22), wait=3):
                logging.warning(
                    "Skill replace: confirm %d/2 not found after %s %s.",
                    n + 1, sinner_name, chosen)
                break
            confirms += 1
            time.sleep(0.6)

        # If srep_menu is still on screen the swap-button click missed
        # (chevron templates score low). Retry up to twice.
        for retry in range(2):
            time.sleep(0.6)
            if not LocateGray.check(PTH[_SKILL_REPLACE_MENU],
                                    wait=False, conf=0.85) \
               and not LocateRGB.check(PTH[_SKILL_REPLACE_MENU],
                                       wait=False, conf=0.85):
                break
            logging.info(
                "Skill replace: %s %s menu still visible; retry %d/2.",
                sinner_name, chosen, retry + 1)
            if not tap_center(swap_tpl, tsize=(46, 22), wait=2):
                logging.warning(
                    "Skill replace: swap button gone on retry %d.",
                    retry + 1)
                break
            time.sleep(0.5)
            extra_confirms = 0
            for n in range(2):
                if not tap_center("packconfirm", tsize=(60, 22), wait=3):
                    break
                extra_confirms += 1
                time.sleep(0.6)
            confirms += extra_confirms

        if confirms == 0:
            # No confirm appeared; treat as no-op (don't decrement quota).
            p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
            continue

        # Commit the swap.
        caps_for_sinner = p.SKILL_REPLACE_REMAINING.setdefault(sinner_name, {})
        caps_for_sinner[chosen] = max(
            0, int(caps_for_sinner.get(chosen, 0) or 0) - 1)
        p.SKILL_REPLACE_SINNERS_THIS_SHOP.add(sinner_name)
        swaps_taken += 1
        p.RUN_SKILL_REPLACES = int(getattr(p, "RUN_SKILL_REPLACES", 0) or 0) + 1
        logging.info(
            "Skill replace: %s %s applied (confirms %d/2). "
            "Run total: %d skill-replace(s).",
            sinner_name, chosen, confirms, p.RUN_SKILL_REPLACES)

    p.SKILL_REPLACE_USED_THIS_SHOP = (
        getattr(p, "SKILL_REPLACE_USED_THIS_SHOP", 0) + swaps_taken
    )
    return swaps_taken


def saikai_skill_replace():
    """SAIKAI: take Ryoshu's S1 -> S3 swap once per run - the first thing done
    at the rest shop. Hard-coded to Ryoshu (the generic do_skill_replace never
    runs for SAIKAI). Locates her market skill-swap icon (ryoshuskillreplace),
    opens it, and applies the S1 -> S3 swap (ryoshus1s3)."""
    if getattr(p, "SAIKAI_S3_DONE", False):
        return False
    if "ryoshuskillreplace" not in PTH or "ryoshus1s3" not in PTH:
        return False

    # Click Ryoshu's skill-swap icon. wait=3 so the market shelf has time to
    # render after the shop opens; wait=0 was missing it and skipping the swap.
    if not tap_center("ryoshuskillreplace", tsize=(46, 22), wait=3):
        return False
    logging.info("SAIKAI: Ryoshu skill-swap icon found - applying S1 -> S3.")
    time.sleep(0.6)

    if not tap_center("ryoshus1s3", tsize=(46, 22), wait=3):
        logging.warning("SAIKAI: S1->S3 option not found after opening the "
                        "swap menu; backing out.")
        gui.press("escape"); time.sleep(0.4)
        return False

    time.sleep(0.5)
    confirms = 0
    for n in range(2):                      # packconfirm shows up twice
        if not tap_center("packconfirm", tsize=(60, 22), wait=3):
            logging.warning("SAIKAI: skill-replace confirm %d/2 not found.", n + 1)
            break
        confirms += 1
        time.sleep(0.6)

    if confirms == 0:
        gui.press("escape"); time.sleep(0.4)    # fail-safe: never leave it open
        return False
    p.SAIKAI_S3_DONE = True
    logging.info("SAIKAI: Ryoshu S1 -> S3 skill replace complete.")
    return True


def shop():
    if getattr(p, "SKIP_RESTSHOP", False):
        # Two cases: (1) called on a non-shop screen -> return False so caller
        # moves on; (2) actually on a shop screen -> leave() to exit cleanly
        # (returning False here would spin forever since the screen never goes away).
        if now_click.button("return"):
            time.sleep(0.5)
        if now.button("shop") or now.button("supershop"):
            logging.info(
                "Skipping rest shop (Behaviour: Skip rest shop) - "
                "leaving shop screen.")
            p.SUPER = "shop" if now.button("shop") else "supershop"
            try:
                leave()
            except Exception as exc:
                logging.warning(
                    "Skip rest shop: leave() failed (%s); will retry.", exc)
            return True
        return False

    if now_click.button("return"): time.sleep(0.5)

    if now.button("shop"): p.SUPER = "shop"
    elif now.button("supershop"):
        # Super shop exists only on Hard, so its button means we ARE on Hard
        # even if the Normal->Hard flip lagged. Gated to HARD_TARGET.
        p.SUPER = "supershop"
        if p.HARD_TARGET:
            p.HARD = True
    else: return False
    print("shop check")
    time.sleep(0.2)
    # Per-visit reset (cap applies across refreshes within one visit).
    p.SKILL_REPLACE_USED_THIS_SHOP = 0
    p.SKILL_REPLACE_SINNERS_THIS_SHOP = set()
    p.RUN_SHOP_VISITS = int(getattr(p, "RUN_SHOP_VISITS", 0) or 0) + 1
    logging.info("shop: entry (%s, run shop-count now %d)",
                 p.SUPER, p.RUN_SHOP_VISITS)
    saikai = p.RUN_SCRIPT == "saikai_ryoshu"
    if saikai:
        saikai_skill_replace()                  # Ryoshu only; never the generic path
    else:
        do_skill_replace()

    if now.button("Confirm"):
        if not input_with_fallback(
            "space", 
            lambda: now_click.button("Confirm"),
            lambda: wait_while_condition(
                lambda: now.button("Confirm"),
                timer=2
            )
        ): return False

    if p.DEAD > 0 and p.HARD:
        # SAIKAI runs solo Ryoshu and depends on the other six being down;
        # both revive and heal are banned.
        if p.RUN_SCRIPT == "saikai_ryoshu":
            logging.info("SAIKAI: %d sinner(s) down - skipping revive AND heal "
                         "(both banned for this run).", p.DEAD)
        else:
            revive_idiots()
            heal_all()

    # High-floor extra heals: skip for SAIKAI for the same reason.
    if p.LVL > 11 and p.RUN_SCRIPT != "saikai_ryoshu":
        for _ in range(min(p.LVL - 11, 3)):
            heal_all()

    if p.EXTREME:
        for _ in range(1 + int(p.SUPER == "supershop")):
            buy_skill3()

    if p.LVL == 1:
        ClickAction((250, 581), ver="power").execute(click)
        if not loc_shop.button("+", "fuse_shelf", conf=0.95):
            # genuinely on the first floor
            try:
                if p.RUN_SCRIPT == "thrill":
                    thrill_market_f1()
                else:
                    enhance(p.GIFTS[0]["uptie1"], floor1=True)
                    buy_loop({3: 2}, floor1=True)
            except RuntimeError:
                handle_fuckup()
        else:
            # bot was started midway; not the first floor
            p.LVL = 2
            close_panel()
    # Range includes the boss-prep floor (F5 Normal, F16 Extreme). Using `>`
    # excluded those, so SKIP=on would waste the last gear-up chance.
    if 5 + p.EXTREME*11 >= p.LVL > 1 or not p.SKIP:
        if p.RUN_SCRIPT == "thrill" and getattr(p, "THRILL_DONE", False):
            # THRILL F2: top off the thrill enhance (no-op if F1 fully landed).
            # F3+: nothing (run forfeits after F3; don't spend leftover budget).
            if p.LVL == 2:
                logging.info("THRILL: F2 market - topping off thrill enhance only.")
                try:
                    enhance({"thrill": 4})
                except Exception as exc:
                    logging.warning("THRILL: F2 thrill enhance failed: %s", exc)
            else:
                logging.info("THRILL: F%d market - no market actions.", p.LVL)
        else:
            buy_some(rerolls=0, priority=True)
            fuse_loop()
    
    if p.EXTREME:
        win_click(1489, 177, tsize=(180, 53))
        connection()
        time.sleep(0.1)
        for _ in range(1 + int(p.SUPER == "supershop")):
            buy_skill3()
    
    time.sleep(0.1)
    leave()
    return True