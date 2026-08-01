#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <unordered_map>

#ifdef _WIN32
#define TH06_EXPORT extern "C" __declspec(dllexport)
#else
#define TH06_EXPORT extern "C"
#endif

namespace {

struct Aabb {
    float left;
    float top;
    float right;
    float bottom;
};

struct LaserHazard {
    float originX;
    float originY;
    float angle;
    float centerOffset;
    float sizeX;
    float sizeY;
};

struct SafeResult {
    std::int32_t safe;
    float clearance;
    float finalX;
    float finalY;
};

struct Direction {
    std::int32_t dx;
    std::int32_t dy;
};

struct ControlAction {
    Direction direction;
    bool focused;
};

constexpr std::int32_t kFocusedActionCount = 9;
constexpr std::int32_t kControlActionCount = 18;
constexpr ControlAction kActions[kControlActionCount] = {
    {{0, 0}, true}, {{0, -1}, true}, {{0, 1}, true},
    {{-1, 0}, true}, {{1, 0}, true}, {{-1, -1}, true},
    {{1, -1}, true}, {{-1, 1}, true}, {{1, 1}, true},
    {{0, 0}, false}, {{0, -1}, false}, {{0, 1}, false},
    {{-1, 0}, false}, {{1, 0}, false}, {{-1, -1}, false},
    {{1, -1}, false}, {{-1, 1}, false}, {{1, 1}, false},
};
constexpr std::uint16_t kActionMasks[kControlActionCount] = {
    0x04U, 0x14U, 0x24U, 0x44U, 0x84U,
    0x54U, 0x94U, 0x64U, 0xA4U,
    0x00U, 0x10U, 0x20U, 0x40U, 0x80U,
    0x50U, 0x90U, 0x60U, 0xA0U,
};
constexpr std::uint16_t kControlBits[5] = {
    0x20U, 0x04U, 0x40U, 0x80U, 0x10U,
};
constexpr std::int32_t kDelays[4] = {0, 1, 2, 3};

ControlAction actionFromInput(std::uint16_t mask) {
    ControlAction result{{0, 0}, (mask & 0x04U) != 0U};
    if ((mask & 0x10U) != 0U) {
        result.direction.dy = -1;
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    } else if ((mask & 0x20U) != 0U) {
        result.direction.dy = 1;
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    } else {
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    }
    return result;
}

bool sameAction(ControlAction left, ControlAction right) {
    return left.direction.dx == right.direction.dx
        && left.direction.dy == right.direction.dy
        && left.focused == right.focused;
}

std::int32_t transitionActions(
    std::uint16_t currentMask,
    std::uint16_t targetMask,
    ControlAction output[5]
) {
    currentMask &= 0xF4U;
    targetMask &= 0xF4U;
    std::uint16_t prefixMask = currentMask;
    const ControlAction current = actionFromInput(currentMask);
    const ControlAction target = actionFromInput(targetMask);
    std::int32_t count = 0;
    const auto append = [&](ControlAction prefix) {
        if (sameAction(prefix, current) || sameAction(prefix, target)) return;
        for (std::int32_t index = 0; index < count; ++index) {
            if (sameAction(prefix, output[index])) return;
        }
        output[count++] = prefix;
    };
    // Keyboard::_sync sorts control key names as down, focus, left, right, up,
    // publishing every release before every press in one SendInput batch.
    for (const std::uint16_t bit : kControlBits) {
        if ((currentMask & bit) != 0U && (targetMask & bit) == 0U) {
            prefixMask &= ~bit;
            append(actionFromInput(prefixMask));
        }
    }
    for (const std::uint16_t bit : kControlBits) {
        if ((targetMask & bit) != 0U && (currentMask & bit) == 0U) {
            prefixMask |= bit;
            append(actionFromInput(prefixMask));
        }
    }
    return count;
}

ControlAction scheduledAction(
    std::int32_t frame,
    std::int32_t delay,
    ControlAction current,
    ControlAction target,
    const ControlAction* transition
) {
    if (transition != nullptr) {
        if (frame < delay) return current;
        if (frame == delay) return *transition;
        return target;
    }
    return frame <= delay ? current : target;
}

void stepPlayer(
    float& x,
    float& y,
    ControlAction action,
    float normalCardinal,
    float focusCardinal,
    float normalDiagonal,
    float focusDiagonal
) {
    const bool diagonal = action.direction.dx != 0 && action.direction.dy != 0;
    const float speed = action.focused
        ? (diagonal ? focusDiagonal : focusCardinal)
        : (diagonal ? normalDiagonal : normalCardinal);
    x = std::clamp(
        x + static_cast<float>(action.direction.dx) * speed, 8.0F, 376.0F
    );
    y = std::clamp(
        y + static_cast<float>(action.direction.dy) * speed, 16.0F, 432.0F
    );
}

float signedClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const Aabb& hazard
) {
    const float gapX = std::max(
        hazard.left - (playerX + playerHalfWidth),
        (playerX - playerHalfWidth) - hazard.right
    );
    const float gapY = std::max(
        hazard.top - (playerY + playerHalfHeight),
        (playerY - playerHalfHeight) - hazard.bottom
    );
    if (gapX <= 0.0F && gapY <= 0.0F) return std::max(gapX, gapY);
    return std::hypot(std::max(0.0F, gapX), std::max(0.0F, gapY));
}

bool withinMargin(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const Aabb& hazard,
    float collisionMargin
) {
    const float gapX = std::max(
        hazard.left - (playerX + playerHalfWidth),
        (playerX - playerHalfWidth) - hazard.right
    );
    const float gapY = std::max(
        hazard.top - (playerY + playerHalfHeight),
        (playerY - playerHalfHeight) - hazard.bottom
    );
    const float positiveX = std::max(0.0F, gapX);
    const float positiveY = std::max(0.0F, gapY);
    return positiveX * positiveX + positiveY * positiveY
        <= collisionMargin * collisionMargin;
}

float signedLaserClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const LaserHazard& laser
) {
    const float dx = playerX - laser.originX;
    const float dy = playerY - laser.originY;
    const float sine = std::sin(laser.angle);
    const float cosine = std::cos(laser.angle);
    const float localX = cosine * dx + sine * dy;
    const float localY = cosine * dy - sine * dx;
    const Aabb box{
        laser.centerOffset - laser.sizeX / 2.0F,
        -laser.sizeY / 2.0F,
        laser.centerOffset + laser.sizeX / 2.0F,
        laser.sizeY / 2.0F,
    };
    return signedClearance(localX, localY, playerHalfWidth, playerHalfHeight, box);
}

bool withinLaserMargin(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const LaserHazard& laser,
    float collisionMargin
) {
    const float dx = playerX - laser.originX;
    const float dy = playerY - laser.originY;
    const float sine = std::sin(laser.angle);
    const float cosine = std::cos(laser.angle);
    const float localX = cosine * dx + sine * dy;
    const float localY = cosine * dy - sine * dx;
    const Aabb box{
        laser.centerOffset - laser.sizeX / 2.0F,
        -laser.sizeY / 2.0F,
        laser.centerOffset + laser.sizeX / 2.0F,
        laser.sizeY / 2.0F,
    };
    return withinMargin(
        localX,
        localY,
        playerHalfWidth,
        playerHalfHeight,
        box,
        collisionMargin
    );
}

bool safeAtFrame(
    float x,
    float y,
    float playerHalfWidth,
    float playerHalfHeight,
    std::int32_t frameIndex,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    float* clearance
) {
    const std::uint32_t bulletStart = bulletOffsets[frameIndex];
    const std::uint32_t bulletEnd = bulletOffsets[frameIndex + 1];
    for (std::uint32_t index = bulletStart; index < bulletEnd; ++index) {
        if (clearance == nullptr) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) return false;
            continue;
        }
        const float value = signedClearance(
            x, y, playerHalfWidth, playerHalfHeight, bullets[index]
        );
        *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    const std::uint32_t laserStart = laserOffsets[frameIndex];
    const std::uint32_t laserEnd = laserOffsets[frameIndex + 1];
    for (std::uint32_t index = laserStart; index < laserEnd; ++index) {
        if (clearance == nullptr) {
            if (withinLaserMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                lasers[index],
                collisionMargin
            )) return false;
            continue;
        }
        const float value = signedLaserClearance(
            x, y, playerHalfWidth, playerHalfHeight, lasers[index]
        );
        *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    return true;
}

std::uint64_t positionKey(float x, float y) {
    std::uint32_t xBits;
    std::uint32_t yBits;
    std::memcpy(&xBits, &x, sizeof(xBits));
    std::memcpy(&yBits, &y, sizeof(yBits));
    return (static_cast<std::uint64_t>(xBits) << 32U) | yBits;
}

bool cachedSafeAtFrame(
    float x,
    float y,
    float playerHalfWidth,
    float playerHalfHeight,
    std::int32_t frameIndex,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::array<std::unordered_map<std::uint64_t, bool>, 64>& cache
) {
    auto& frameCache = cache[frameIndex];
    const std::uint64_t key = positionKey(x, y);
    const auto found = frameCache.find(key);
    if (found != frameCache.end()) return found->second;
    const bool safe = safeAtFrame(
        x,
        y,
        playerHalfWidth,
        playerHalfHeight,
        frameIndex,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        nullptr
    );
    frameCache.emplace(key, safe);
    return safe;
}

}  // namespace

TH06_EXPORT std::int32_t th06_certify_actions(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    SafeResult* output,
    SafeResult* ageZeroOutput
) {
    if (
        horizon <= 0 || horizon > 64 || bulletOffsets == nullptr ||
        laserOffsets == nullptr || output == nullptr || ageZeroOutput == nullptr
    ) {
        return -1;
    }
    const ControlAction current = actionFromInput(inputMask);

    for (std::int32_t actionIndex = 0; actionIndex < kControlActionCount; ++actionIndex) {
        if ((candidateMask & (1U << actionIndex)) == 0U) {
            output[actionIndex] = SafeResult{0, 0.0F, playerX, playerY};
            ageZeroOutput[actionIndex] = SafeResult{0, 0.0F, playerX, playerY};
            continue;
        }
        SafeResult result{1, 999.0F, playerX, playerY};
        SafeResult ageZeroResult{0, 0.0F, playerX, playerY};
        ControlAction transitions[5];
        const std::int32_t transitionCount = transitionActions(
            inputMask, kActionMasks[actionIndex], transitions
        );
        for (const std::int32_t delay : kDelays) {
            float normalFinalX = playerX;
            float normalFinalY = playerY;
            const std::int32_t branchCount = 1 + (delay > 0 ? transitionCount : 0);
            for (std::int32_t branch = 0; branch < branchCount; ++branch) {
                const ControlAction* transition = branch == 0
                    ? nullptr
                    : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                for (std::int32_t frame = 1; frame <= horizon; ++frame) {
                    stepPlayer(
                        x,
                        y,
                        scheduledAction(
                            frame, delay, current, kActions[actionIndex], transition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                    if (!safeAtFrame(
                        x,
                        y,
                        playerHalfWidth,
                        playerHalfHeight,
                        frame - 1,
                        bulletOffsets,
                        bullets,
                        laserOffsets,
                        lasers,
                        collisionMargin,
                        &result.clearance
                    )) {
                        result.safe = 0;
                        break;
                    }
                }
                if (result.safe == 0) break;
                if (branch == 0) {
                    normalFinalX = x;
                    normalFinalY = y;
                }
            }
            if (delay == kDelays[2]) {
                ageZeroResult = result;
                ageZeroResult.finalX = normalFinalX;
                ageZeroResult.finalY = normalFinalY;
            }
            if (result.safe == 0) break;
            if (delay == kDelays[3]) {
                result.finalX = normalFinalX;
                result.finalY = normalFinalY;
            }
        }
        output[actionIndex] = result;
        ageZeroOutput[actionIndex] = ageZeroResult;
    }
    return 0;
}

// This is a proposal score only. candidateMask must already come from the
// hard authority; the result can rank those candidates but cannot add one.
TH06_EXPORT std::int32_t th06_replanning_scores(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t split,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::int32_t* output
) {
    if (
        split <= 0 || horizon <= split || horizon > 64 ||
        bulletOffsets == nullptr || laserOffsets == nullptr || output == nullptr
    ) {
        return -1;
    }
    const ControlAction current = actionFromInput(inputMask);
    // Delivery and transition branches revisit the same small movement
    // lattice thousands of times.  Cache exact float positions per future
    // frame so each dense hazard slice is scanned once without changing the
    // conservative branch set or its scores.
    std::array<std::unordered_map<std::uint64_t, bool>, 64> safetyCache;
    for (std::int32_t firstIndex = 0; firstIndex < kControlActionCount; ++firstIndex) {
        output[firstIndex] = 0;
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;
        ControlAction firstTransitions[5];
        const std::int32_t firstTransitionCount = transitionActions(
            inputMask, kActionMasks[firstIndex], firstTransitions
        );
        std::int32_t worstBranchCount = kFocusedActionCount;
        for (const std::int32_t firstDelay : kDelays) {
            const std::int32_t firstBranchCount = 1 + (
                firstDelay > 0 ? firstTransitionCount : 0
            );
            for (std::int32_t firstBranch = 0; firstBranch < firstBranchCount; ++firstBranch) {
                const ControlAction* firstTransition = firstBranch == 0
                    ? nullptr
                    : &firstTransitions[firstBranch - 1];
                float splitX = playerX;
                float splitY = playerY;
                for (std::int32_t frame = 1; frame <= split; ++frame) {
                    stepPlayer(
                        splitX,
                        splitY,
                        scheduledAction(
                            frame,
                            firstDelay,
                            current,
                            kActions[firstIndex],
                            firstTransition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                }
                std::int32_t continuationCount = 0;
                for (
                    std::int32_t secondIndex = 0;
                    secondIndex < kFocusedActionCount;
                    ++secondIndex
                ) {
                    ControlAction secondTransitions[5];
                    const std::int32_t secondTransitionCount = transitionActions(
                        kActionMasks[firstIndex],
                        kActionMasks[secondIndex],
                        secondTransitions
                    );
                    bool survived = true;
                    for (const std::int32_t secondDelay : kDelays) {
                        const std::int32_t secondBranchCount = 1 + (
                            secondDelay > 0 ? secondTransitionCount : 0
                        );
                        for (
                            std::int32_t secondBranch = 0;
                            secondBranch < secondBranchCount;
                            ++secondBranch
                        ) {
                            const ControlAction* secondTransition = secondBranch == 0
                                ? nullptr
                                : &secondTransitions[secondBranch - 1];
                            float x = splitX;
                            float y = splitY;
                            for (std::int32_t frame = split + 1; frame <= horizon; ++frame) {
                                const std::int32_t elapsed = frame - split;
                                stepPlayer(
                                    x,
                                    y,
                                    scheduledAction(
                                        elapsed,
                                        secondDelay,
                                        kActions[firstIndex],
                                        kActions[secondIndex],
                                        secondTransition
                                    ),
                                    normalSpeed,
                                    focusSpeed,
                                    normalDiagonalSpeed,
                                    focusDiagonalSpeed
                                );
                                if (!cachedSafeAtFrame(
                                    x,
                                    y,
                                    playerHalfWidth,
                                    playerHalfHeight,
                                    frame - 1,
                                    bulletOffsets,
                                    bullets,
                                    laserOffsets,
                                    lasers,
                                    collisionMargin,
                                    safetyCache
                                )) {
                                    survived = false;
                                    break;
                                }
                            }
                            if (!survived) break;
                        }
                        if (!survived) break;
                    }
                    continuationCount += static_cast<std::int32_t>(survived);
                }
                worstBranchCount = std::min(worstBranchCount, continuationCount);
            }
        }
        output[firstIndex] = worstBranchCount;
    }
    return 0;
}
